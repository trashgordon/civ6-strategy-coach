"""The staged pipeline (PIPELINE=staged): decide, check, then write.

The single coach decides and writes in one pass, and every check we have runs on its
prose afterwards — regex over sentences, tuned to stay quiet, so it misses things and
can only flag what it catches. Here the decisions come first, as JSON, where checking
them is exact rather than heuristic:

1. A strategist (at medium effort — the thinking is the point) returns the plan's
   decisions as structured data.
2. Those are checked against the installed game data: every name real, both paths in
   prerequisite order and in the right tree, each promotion belonging to its governor,
   benchmark turns rising. Anything wrong goes back to the strategist, with the exact
   errors, for up to two repair rounds.
3. The writer — the coach's own system prompt from the brief, unchanged, at low effort
   since nothing is left to decide — turns the checked decisions into the plan.

Everything degrades with the game data: without it the check has nothing to check
against and the decisions go straight to the writer.
"""

import json
from typing import Any

from . import facts, llm, tree
from .prompts import STRATEGIST_TASK, WRITER_TASK
from .gamedata import match_civ
from .ruleset import DEFAULT_RULESET, RULESETS

STRATEGIST_EFFORT = "medium"
WRITER_EFFORT = "low"
STRATEGIST_TOKENS = 12000
WRITER_TOKENS = 6000
MAX_REPAIRS = 2



# ---------------------------------------------------------------------------- parsing


def parse_decisions(text: str) -> dict | None:
    """The JSON object in a reply, tolerating fences or a stray sentence around it."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


# ------------------------------------------------------------------------- validation


def _fold(name: str) -> str:
    return tree._plain(str(name)).strip().lower()


def _lookup(names) -> dict[str, str]:
    return {_fold(n): n for n in names}


def _known(raw: Any, lookup: dict[str, str]) -> str | None:
    """The real name `raw` refers to: exact, or a real name followed by an aside —
    "Petra (does nothing for a conquest game)" is Petra. Longest name wins."""
    folded = _fold(raw)
    if folded in lookup:
        return lookup[folded]
    for key in sorted(lookup, key=len, reverse=True):
        if folded.startswith(key) and not folded[len(key):len(key) + 1].isalnum():
            return lookup[key]
    return None


def _strings(value: Any) -> list[str]:
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


def check_decisions(decisions: dict, ruleset: str | None) -> list[str]:
    """Every way the decisions contradict the installed game data. Empty when clean,
    or when there's no game data to check against."""
    errors: list[str] = []
    label = ruleset if ruleset in RULESETS else DEFAULT_RULESET
    data = tree.for_ruleset(label)
    loaded = facts._load()

    if not match_civ(str(decisions.get("civ", ""))):
        errors.append(f"civ: {decisions.get('civ')!r} isn't a civilization I recognise.")

    if data:
        ancestors = tree._index(label)["ancestors"]
        for key, bucket, other, label_one, label_other in (
            ("tech_path", "technologies", "civics", "technology", "civic"),
            ("civic_path", "civics", "technologies", "civic", "technology"),
        ):
            mine, theirs = _lookup(data.get(bucket, {})), _lookup(data.get(other, {}))
            path: list[str] = []
            for raw in _strings(decisions.get(key)):
                name = _known(raw, mine)
                if name:
                    path.append(name)
                elif _known(raw, theirs):
                    errors.append(f"{key}: {_known(raw, theirs)} is a {label_other}, not a {label_one} — move it to the other path.")
                else:
                    errors.append(f"{key}: {raw!r} isn't a {label_one} in {label}.")
            for i, name in enumerate(path):
                for later in path[i + 1 :]:
                    if later in ancestors.get((name, bucket), ()):
                        errors.append(f"{key}: {name} is listed before {later}, but {name} needs {later} first.")

        wonders = _lookup(data.get("wonders", {}))
        for entry in decisions.get("wonders") or []:
            name = entry.get("name") if isinstance(entry, dict) else entry
            if name and not _known(name, wonders):
                errors.append(f"wonders: {name!r} isn't a wonder in {label}.")
        skip = decisions.get("wonder_to_skip")
        if skip and not _known(skip, wonders):
            errors.append(f"wonder_to_skip: {skip!r} isn't a wonder in {label}.")

    for key, category in (("governments", "governments"), ("policy_cards", "policy_cards")):
        known = _lookup(loaded.get(category, ()))
        if known:
            for raw in _strings(decisions.get(key)):
                if not _known(raw, known):
                    errors.append(f"{key}: {raw!r} isn't a real {category.replace('_', ' ')[:-1]}.")

    states = _lookup(e["name"] for e in facts.city_states())
    if states:
        for entry in decisions.get("city_states") or []:
            name = entry.get("name") if isinstance(entry, dict) else entry
            if name and not _known(name, states):
                errors.append(f"city_states: {name!r} isn't a city-state in the game.")

    kits = {_fold(k["governor"]): k for k in facts.governor_kits()}
    if kits:
        for entry in decisions.get("governors") or []:
            if not isinstance(entry, dict):
                continue
            kit = kits.get(_fold(_known(entry.get("name", ""), {k: k for k in kits}) or ""))
            if kit is None:
                errors.append(f"governors: {entry.get('name')!r} isn't a governor.")
                continue
            own = _lookup(p["name"] for p in kit.get("promotions", []))
            for promo in _strings(entry.get("promotions")):
                if not _known(promo, own):
                    errors.append(
                        f"governors: {promo!r} isn't one of {kit['governor']}'s promotions "
                        f"(theirs: {', '.join(sorted(own.values()))})."
                    )

    turns = [b.get("turn") for b in decisions.get("benchmarks") or [] if isinstance(b, dict)]
    if any(not isinstance(t, (int, float)) for t in turns):
        errors.append("benchmarks: every benchmark needs a numeric turn.")
    elif turns != sorted(turns):
        errors.append(f"benchmarks: turns must rise in order, got {turns}.")
    return errors


def unlocks_for(decisions: dict, ruleset: str | None) -> dict[str, str]:
    """What unlocks each decided wonder, government and card, and the civ's uniques.

    The writer explains the decisions, and explaining a wonder invites saying what it
    comes from — which it then recalled wrongly (Taj Mahal from Astronomy; it's
    Humanism). Handing it the answer leaves nothing to recall.
    """
    data = tree.for_ruleset(ruleset if ruleset in RULESETS else DEFAULT_RULESET)
    if not data:
        return {}
    items = {_fold(u["name"]): u for u in data.get("unlocks", [])}

    def label(item: dict) -> str:
        return f"{item['by']} ({'tech' if item['tree'] == 'technology' else 'civic'})"

    named = [e.get("name") if isinstance(e, dict) else e for e in decisions.get("wonders") or []]
    named += [decisions.get("wonder_to_skip")]
    named += _strings(decisions.get("governments")) + _strings(decisions.get("policy_cards"))
    out: dict[str, str] = {}
    for raw in named:
        if not raw:
            continue
        name = _known(raw, {k: k for k in items})
        if name:
            out[items[name]["name"]] = label(items[name])
    civ = match_civ(str(decisions.get("civ", "")))
    for item in data.get("unlocks", []):
        if civ and match_civ(item.get("civ") or "") == civ:
            out[item["name"]] = label(item)
    return out


# --------------------------------------------------------------------------- pipeline


def _add(total: dict, result: llm.Completion) -> None:
    total.setdefault("calls", []).append({
        "model": result.model, "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens, "cost_usd": result.cost_usd,
        "cache_write_tokens": result.cache_write_tokens,
        "cache_read_tokens": result.cache_read_tokens,
    })
    for field in ("prompt_tokens", "completion_tokens", "cost_usd",
                  "cache_write_tokens", "cache_read_tokens"):
        value = getattr(result, field)
        if value is not None:
            total[field] = (total.get(field) or 0) + value


async def draft_plan(*, config: dict, user_prompt: str, system_prompt: str) -> llm.Completion:
    """Decide → check → repair → write. Returns one Completion summed over every call,
    with `detail` recording what the check found and whether the repairs cleared it."""
    ruleset = config.get("ruleset")
    totals: dict = {}
    strategist_prompt = f"{user_prompt}\n\n{STRATEGIST_TASK}"

    reply = await llm.complete(system_prompt, strategist_prompt, STRATEGIST_TOKENS,
                               reasoning_effort=STRATEGIST_EFFORT)
    _add(totals, reply)
    decisions = parse_decisions(reply.text)
    errors = check_decisions(decisions, ruleset) if decisions else ["The reply wasn't a JSON object."]
    first_errors, repairs = list(errors), 0

    while errors and repairs < MAX_REPAIRS:
        repairs += 1
        fix = (
            f"{strategist_prompt}\n\nYour previous decisions:\n{reply.text}\n\n"
            "They don't match the game data:\n- " + "\n- ".join(errors) +
            "\n\nReply with the corrected JSON object only, changing only what's needed."
        )
        reply = await llm.complete(system_prompt, fix, STRATEGIST_TOKENS,
                                   reasoning_effort=STRATEGIST_EFFORT)
        _add(totals, reply)
        fixed = parse_decisions(reply.text)
        if fixed:
            decisions = fixed
            errors = check_decisions(decisions, ruleset)
        else:
            errors = ["The reply wasn't a JSON object."]

    if not decisions:
        raise llm.LLMError("The strategist never produced usable decisions. Try again.")

    brief = {**decisions, "unlocked_by": unlocks_for(decisions, ruleset)}
    written = await llm.complete(
        system_prompt,
        f"{user_prompt}\n\n{WRITER_TASK}{json.dumps(brief, indent=1, ensure_ascii=False)}",
        WRITER_TOKENS,
        reasoning_effort=WRITER_EFFORT,
    )
    _add(totals, written)

    return llm.Completion(
        text=written.text,
        model=written.model,
        truncated=written.truncated,
        detail={
            "pipeline": "staged",
            "decisions": decisions,
            "errors_found": first_errors,
            "repairs": repairs,
            "errors_left": errors,
            # One entry per model call, so the cost tracker can show each of them.
            "calls": totals.pop("calls", []),
        },
        **totals,
    )
