"""Blind A/B pairs from two eval runs, for rating in the app's Rate tab.

    python -m evals.pairs make RUN_A RUN_B --experiment single-vs-staged
    python -m evals.pairs report

The eval's checks say whether a plan is *correct*; they can't say whether it's *good*.
That takes a human reading two plans for the same brief without knowing which setting
wrote which. So: generate two runs with `evals.run` under the two settings you want to
compare (PIPELINE, REASONING_EFFORT, ...), pair their plans brief by brief here, and rate
them in the app. RUN_A / RUN_B are result files in data/evals/, by path or by name
(the timestamp is enough, e.g. 20260919-190151).

Costs nothing: it only reads saved runs.
"""

import argparse
import json
import random
import sys
from pathlib import Path

from backend import db
from backend.generation import tidy_headers
from evals.run import BRIEFS, RESULTS


def _find(run: str) -> Path:
    path = Path(run)
    if path.is_file():
        return path
    matches = sorted(RESULTS.glob(f"{run}*.json"))
    if len(matches) != 1:
        raise SystemExit(f"Couldn't find exactly one saved run matching {run!r} in {RESULTS}.")
    return matches[0]


def _label(data: dict) -> str:
    fp = data.get("fingerprint", {})
    parts = [fp.get("pipeline") or "single", f"effort {fp.get('reasoning_effort', '?')}"]
    return f"{', '.join(parts)} ({data.get('started_at', '')[:16].replace('T', ' ')})"


def _briefs() -> tuple[dict, dict[str, dict]]:
    data = json.loads(BRIEFS.read_text())
    return data["base_config"], {b["id"]: b for b in data["briefs"]}


def make(run_a: str, run_b: str, experiment: str, label_a: str | None, label_b: str | None,
         seed: int | None) -> int:
    path_a, path_b = _find(run_a), _find(run_b)
    a, b = json.loads(path_a.read_text()), json.loads(path_b.read_text())
    if a["fingerprint"].get("briefs_sha") != b["fingerprint"].get("briefs_sha"):
        print("  warning: the briefs changed between these runs — pairs may not match up",
              file=sys.stderr)

    db.migrate()
    existing = [s for s in db.rating_summary() if s["experiment"] == experiment]
    if existing:
        raise SystemExit(f"An experiment called {experiment!r} already exists; pick another name.")

    base, briefs = _briefs()
    plans_b = {(r["brief"], r["attempt"]): r["plan"] for r in b["results"] if "plan" in r}
    rng = random.Random(seed)
    made = 0
    for r in a["results"]:
        key = (r.get("brief"), r.get("attempt"))
        if "plan" not in r or key not in plans_b:
            continue
        brief = briefs.get(r["brief"], {"id": r["brief"]})
        config = {**base, **brief.get("config", {})}
        db.insert_rating_pair(
            experiment=experiment,
            brief_id=r["brief"],
            brief={**{k: v for k, v in brief.items() if k != "why"}, "config": config},
            label_a=label_a or _label(a),
            label_b=label_b or _label(b),
            # The app tidies headers before saving; do the same here so formatting
            # can't give away which setting wrote a plan.
            plan_a=tidy_headers(r["plan"]),
            plan_b=tidy_headers(plans_b[key]),
            left_is_a=rng.random() < 0.5,
        )
        made += 1
    print(f"  {made} pairs in {experiment!r}: A = {label_a or _label(a)}\n"
          f"  {' ' * len(str(made))}           B = {label_b or _label(b)}\n"
          f"  Rate them in the app's Rate tab.")
    return 0 if made else 1


def report() -> int:
    db.migrate()
    summary = db.rating_summary()
    if not summary:
        print("  No rating pairs yet. Make some with: python -m evals.pairs make RUN_A RUN_B -e NAME")
        return 0
    for s in summary:
        decided = s["a_wins"] + s["b_wins"]
        p = s["p_value"]
        verdict = "not enough rated yet" if p is None else (
            f"p = {p:.3f} — {'a real difference' if p < 0.05 else 'could still be chance'}"
        )
        print(f"\n  {s['experiment']}  ({s['pairs'] - s['unrated']}/{s['pairs']} rated)")
        print(f"    A  {s['label_a']:48} {s['a_wins']:>3} wins")
        print(f"    B  {s['label_b']:48} {s['b_wins']:>3} wins")
        print(f"       {'ties':48} {s['ties']:>3}")
        print(f"    {verdict}" + (f" ({decided} decided)" if decided else ""))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("make", help="pair two saved eval runs, brief by brief")
    m.add_argument("run_a")
    m.add_argument("run_b")
    m.add_argument("-e", "--experiment", required=True, help="a name for this comparison")
    m.add_argument("--label-a", help="what setting A was (default: read from the run)")
    m.add_argument("--label-b", help="what setting B was")
    m.add_argument("--seed", type=int, help="fix the left/right shuffle")
    sub.add_parser("report", help="how each experiment stands")
    args = parser.parse_args()
    if args.command == "make":
        return make(args.run_a, args.run_b, args.experiment, args.label_a, args.label_b, args.seed)
    return report()


if __name__ == "__main__":
    raise SystemExit(main())
