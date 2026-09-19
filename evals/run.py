"""Run the fixed briefs through the real generation path and score the plans.

    python -m evals.run --dry-run        # what would run, and roughly what it costs
    python -m evals.run                  # run it (asks before spending)
    python -m evals.run --yes --repeat 2 # twice per brief, no prompt

Results go to data/evals/<timestamp>.json (gitignored) and each run is compared with
the previous one, so a prompt change shows up as a before/after number instead of an
impression from one or two generations.

This spends real money on your API key: roughly one cold call plus one warm call per
remaining brief. Spend is logged to your usage totals as kind "eval".
"""

import argparse
import asyncio
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from backend import config, db, facts, generation, llm, prompts
from evals import scoring

BRIEFS = Path(__file__).with_name("briefs.json")
RESULTS = config.REPO_ROOT / "data" / "evals"

# Rough, from measured runs on Claude Sonnet 5 with the full grounding block. Only used
# for the up-front estimate; the real cost is read back from each response.
EST_COLD, EST_WARM = 0.13, 0.035


def load_briefs() -> tuple[dict, list[dict]]:
    data = json.loads(BRIEFS.read_text())
    return data["base_config"], data["briefs"]


def fingerprint() -> dict:
    """What produced this run, so two runs can be told apart in the comparison."""
    grounded = generation.system_prompt()
    return {
        "model": config.model(),
        "reasoning_effort": llm.REASONING_EFFORT,
        "prompt_sha": hashlib.sha256(prompts.BUILD_SYSTEM_PROMPT.encode()).hexdigest()[:10],
        "grounded_prompt_sha": hashlib.sha256(grounded.encode()).hexdigest()[:10],
        "facts_available": facts.available(),
        "briefs_sha": hashlib.sha256(BRIEFS.read_bytes()).hexdigest()[:10],
    }


async def run_one(base: dict, brief: dict, attempt: int) -> dict:
    cfg = {**base, **brief.get("config", {})}
    cfg["modes"] = {**base.get("modes", {}), **brief.get("config", {}).get("modes", {})}
    started = time.monotonic()
    record = {"brief": brief["id"], "attempt": attempt}
    try:
        result = await generation.draft_plan(
            config=cfg,
            civ=brief.get("civ", ""),
            city_philosophy=brief.get("city_philosophy", ""),
            primary_focus=brief.get("primary_focus", ""),
            posture=brief.get("posture", ""),
            playstyle_text=brief.get("playstyle_text", ""),
        )
    except llm.LLMError as exc:
        record["error"] = str(exc)
        return record

    db.insert_api_call(
        kind="eval",
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost_usd=result.cost_usd,
        cache_write_tokens=result.cache_write_tokens,
        cache_read_tokens=result.cache_read_tokens,
    )
    record.update(
        {
            "seconds": round(time.monotonic() - started, 1),
            "cost_usd": result.cost_usd,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "cache_read_tokens": result.cache_read_tokens,
            "plan": result.text,
            "ruleset": cfg.get("ruleset"),
            "score": scoring.score_plan(result.text, cfg.get("ruleset")),
        }
    )
    return record


async def run_all(base, briefs, repeat, concurrency, max_cost) -> list[dict]:
    jobs = [(b, n) for n in range(1, repeat + 1) for b in briefs]
    results: list[dict] = []
    spent = 0.0

    def report(r):
        nonlocal spent
        spent += r.get("cost_usd") or 0.0
        status = "ERROR" if "error" in r else (
            f"{sum(v == scoring.PASS for v in r['score']['checks'].values())}/"
            f"{sum(v != scoring.SKIP for v in r['score']['checks'].values())} checks"
        )
        print(f"  {r['brief']:26} #{r['attempt']}  {status:12} "
              f"${r.get('cost_usd') or 0:.4f}  (spent ${spent:.3f})", flush=True)

    # Warm the prompt cache with one call first. Launched together, every call would be
    # a cold write of the ~36k-token grounded prefix at full price.
    first, rest = jobs[0], jobs[1:]
    r = await run_one(base, *first)
    results.append(r)
    report(r)

    semaphore = asyncio.Semaphore(concurrency)

    async def guarded(job):
        async with semaphore:
            if spent >= max_cost:
                return {"brief": job[0]["id"], "attempt": job[1],
                        "error": f"skipped: budget ${max_cost:.2f} reached"}
            out = await run_one(base, *job)
            report(out)
            return out

    results.extend(await asyncio.gather(*(guarded(j) for j in rest)))
    return results


def summarise(results: list[dict]) -> dict:
    scored = [r for r in results if "score" in r]
    per_check: dict[str, dict[str, int]] = {}
    for r in scored:
        for name, verdict in r["score"]["checks"].items():
            tally = per_check.setdefault(name, {"pass": 0, "fail": 0, "skip": 0})
            tally[verdict] += 1

    def rate(t):
        judged = t["pass"] + t["fail"]
        return round(t["pass"] / judged, 3) if judged else None

    tripped: dict[str, int] = {}
    for r in scored:
        for hit in r["score"]["known_wrong"]:
            tripped[hit["id"]] = tripped.get(hit["id"], 0) + 1

    return {
        "plans": len(scored),
        "errors": len(results) - len(scored),
        "check_pass_rates": {k: rate(v) for k, v in sorted(per_check.items())},
        "overall_pass_rate": rate({
            "pass": sum(t["pass"] for t in per_check.values()),
            "fail": sum(t["fail"] for t in per_check.values()),
        }),
        "speed_scaling": scoring.speed_scaling(
            results, "science-tall-korea", "science-marathon-korea"
        ),
        "mean_words": round(sum(r["score"]["words"] for r in scored) / len(scored)) if scored else None,
        "unverified_total": sum(len(r["score"]["unverified"]) for r in scored),
        "tree_issues_total": sum(len(r["score"].get("tree_issues", [])) for r in scored),
        "known_wrong_tripped": tripped,
        "cost_usd": round(sum(r.get("cost_usd") or 0 for r in results), 4),
    }


def previous_run() -> dict | None:
    runs = sorted(RESULTS.glob("*.json"))
    return json.loads(runs[-1].read_text()) if runs else None


def print_report(summary: dict, fp: dict, before: dict | None) -> None:
    old = (before or {}).get("summary", {})
    old_rates = old.get("check_pass_rates", {})

    def pct(v):
        return "  —  " if v is None else f"{v * 100:4.0f}%"

    def delta(new, prev):
        if new is None or prev is None:
            return ""
        d = round((new - prev) * 100)
        return "" if d == 0 else f"  ({'+' if d > 0 else ''}{d})"

    print("\n  check                          pass rate")
    for name, rate in summary["check_pass_rates"].items():
        print(f"    {name:28} {pct(rate)}{delta(rate, old_rates.get(name))}")
    print(f"    {'speed_scaling (suite)':28} {summary['speed_scaling']}")
    print(f"\n  overall            {pct(summary['overall_pass_rate'])}"
          f"{delta(summary['overall_pass_rate'], old.get('overall_pass_rate'))}")
    print(f"  plans / errors     {summary['plans']} / {summary['errors']}")
    print(f"  mean words         {summary['mean_words']}"
          + (f"  (was {old['mean_words']})" if old.get("mean_words") else ""))
    print(f"  unverified names   {summary['unverified_total']}"
          + (f"  (was {old['unverified_total']})" if "unverified_total" in old else ""))
    if "tree_issues_total" in summary:
        print(f"  tree issues        {summary['tree_issues_total']}"
              + (f"  (was {old['tree_issues_total']})" if "tree_issues_total" in old else ""))
    tripped = summary["known_wrong_tripped"]
    print(f"  known-wrong claims {', '.join(f'{k} x{v}' for k, v in tripped.items()) or 'none'}")
    print(f"  cost               ${summary['cost_usd']:.4f}")

    if before:
        changed = [k for k in ("model", "reasoning_effort", "prompt_sha",
                               "grounded_prompt_sha", "briefs_sha")
                   if before.get("fingerprint", {}).get(k) != fp.get(k)]
        print(f"\n  compared with {before.get('started_at', 'previous run')}; changed since: "
              f"{', '.join(changed) or 'nothing — same prompt, model and briefs'}")
        if "briefs_sha" in changed:
            print("  (the briefs changed, so these numbers aren't directly comparable)")


def rescore(which: str) -> int:
    """Score an earlier run's plans again, after changing the scorer or validator.

    Regenerating would cost money and change the plans too, so you couldn't tell a
    scoring fix from a different sample. This keeps the plans fixed.
    """
    runs = sorted(RESULTS.glob("*.json"))
    path = runs[-1] if which == "latest" and runs else Path(which)
    if not path.is_file():
        print(f"No saved run at {path}.", file=sys.stderr)
        return 2
    data = json.loads(path.read_text())
    before = {"summary": data["summary"], "fingerprint": data["fingerprint"],
              "started_at": f"{data['started_at']} as originally scored"}
    for r in data["results"]:
        if "plan" in r:
            # Runs saved before rulesets were recorded all used the base config's.
            r["score"] = scoring.score_plan(r["plan"], r.get("ruleset"))
    data["summary"] = summarise(data["results"])
    data["rescored_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"  rescored {path.name} ({data['summary']['plans']} plans, no API calls)")
    print_report(data["summary"], data["fingerprint"], before)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="list briefs and estimate cost")
    parser.add_argument("--yes", action="store_true", help="don't ask before spending")
    parser.add_argument("--repeat", type=int, default=1, help="runs per brief (default 1)")
    parser.add_argument("--only", help="comma-separated brief ids to run")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--max-cost", type=float, default=1.00,
                        help="stop launching once this much is spent (default $1.00)")
    parser.add_argument("--rescore", metavar="FILE", nargs="?", const="latest",
                        help="re-apply the current scoring to a saved run's plans, "
                             "for free (default: the latest run)")
    args = parser.parse_args(argv)

    if args.rescore:
        return rescore(args.rescore)

    base, briefs = load_briefs()
    if args.only:
        wanted = {b.strip() for b in args.only.split(",")}
        briefs = [b for b in briefs if b["id"] in wanted]
        if not briefs:
            print(f"No briefs match {sorted(wanted)}.", file=sys.stderr)
            return 2

    calls = len(briefs) * max(1, args.repeat)
    estimate = EST_COLD + EST_WARM * (calls - 1)
    fp = fingerprint()
    print(f"  {calls} generations on {fp['model']} "
          f"(facts {'on' if fp['facts_available'] else 'OFF'}), "
          f"estimated ~${estimate:.2f}, budget ${args.max_cost:.2f}")
    for b in briefs:
        print(f"    {b['id']:26} {b['why'][:70]}")

    if args.dry_run:
        return 0
    hint = llm.missing_key_hint()
    if hint:
        print(f"\n  {hint} isn't set. Add it to .env first.", file=sys.stderr)
        return 2
    if not args.yes:
        if input("\n  Spend it? [y/N] ").strip().lower() not in {"y", "yes"}:
            print("  Not run.")
            return 0

    db.migrate()
    started = datetime.now(timezone.utc)
    print()
    results = asyncio.run(
        run_all(base, briefs, max(1, args.repeat), args.concurrency, args.max_cost)
    )
    summary = summarise(results)
    before = previous_run()

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{started.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({
        "started_at": started.isoformat(timespec="seconds"),
        "fingerprint": fp,
        "summary": summary,
        "results": results,
    }, indent=1, ensure_ascii=False))

    print_report(summary, fp, before)
    print(f"\n  full results: {out.relative_to(config.REPO_ROOT)}")
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
