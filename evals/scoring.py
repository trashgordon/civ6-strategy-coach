"""Deterministic checks on a generated plan.

No model grades another model here: every check is a rule a person could apply by hand,
so a score means the same thing from one run to the next, and a change in the numbers
is a change in the plans rather than in a judge's mood.

Checks return "pass", "fail" or "skip" (skip = can't be judged, usually because the
game facts aren't installed). Expectations are read from the live prompt wherever
possible, so editing the prompt can't silently leave the eval checking the old rules.
"""

import re
from statistics import median

from backend import facts, prompts, tree
from backend.gamedata import match_civ
from backend.titles import civ_from_plan

PASS, FAIL, SKIP = "pass", "fail", "skip"

# Claims we've caught the coach making before. Each is a tripwire: if one of these
# comes back, a fix regressed. Add to this list whenever a new one is found.
KNOWN_WRONG = [
    ("corvee-misattributed",
     r"Corv[ée]e[^\n]{0,80}?\b(settlers?|builders?|infrastructure|expansion|build charges)\b",
     "Corvée is +15% production toward Ancient and Classical wonders."),
    ("research-agreements", r"\bResearch Agreements?\b",
     "Civ V. Civ VI has Research Alliance."),
    ("physics-tech", r"\bPhysics\b", "Civ V tech; not in Civ VI."),
    ("biology-tech", r"\bBiology\b", "Civ V tech; not in Civ VI."),
    ("balista", r"\bBall?ista\b", "No such unit in Civ VI."),
    ("evenkind", r"Evenkind", "The dedication is Exodus of the Evangelists."),
    ("ecumenopolis", r"Ecumenopolis", "Not a Civ VI policy card."),
    ("dramatic-arts", r"\bDramatic Arts\b", "The civic is Drama and Poetry."),
    ("victor-secret-society", r"Victor[^\n]{0,40}Sanguine",
     "Victor is a base-game governor, not a Secret Societies one."),
]


def expected_headers() -> list[str]:
    return re.findall(r"^## (.+)$", prompts.BUILD_SYSTEM_PROMPT, flags=re.M)


def word_cap() -> int:
    match = re.search(r"under roughly (\d+) words", prompts.BUILD_SYSTEM_PROMPT)
    return int(match.group(1)) if match else 1100


# The prompt says "under roughly N words". Failing a plan at N+1 would be stricter than
# the instruction it's checking; mean_words in the summary shows any real creep.
WORD_CAP_TOLERANCE = 0.05


def section(plan: str, name: str) -> str:
    """A section's body, found even if the coach decorated the header.

    "## Timing Benchmarks (Standard speed)" is a header violation, and headers_exact
    reports it. It shouldn't also make every check on that section fail — one mistake
    would then be counted three times.
    """
    match = re.search(
        rf"^##\s+{re.escape(name)}\b[^\n]*$(.*?)(?=^##\s|\Z)", plan, flags=re.S | re.M
    )
    return match.group(1).strip() if match else ""


def _bullets(text: str) -> int:
    return len(re.findall(r"^\s*(?:[-*]|\d+[.)])\s+\S", text, flags=re.M))


def benchmark_turns(plan: str) -> list[int]:
    """Every turn number in Timing Benchmarks: "T60", "turn ~110", "T30–35"."""
    body = section(plan, "Timing Benchmarks")
    found = re.findall(r"\b(?:T|[Tt]urns?\s*~?)\s*(\d{2,4})", body)
    return [int(n) for n in found]


def score_plan(plan: str, ruleset: str | None = None) -> dict:
    """All checks and metrics for one plan."""
    checks: dict[str, str] = {}
    words = len(plan.split())

    headers = re.findall(r"^##\s+(.+?)\s*$", plan, flags=re.M)
    checks["headers_exact"] = PASS if headers == expected_headers() else FAIL
    checks["within_word_cap"] = (
        PASS if words <= word_cap() * (1 + WORD_CAP_TOLERANCE) else FAIL
    )

    playbook = _bullets(section(plan, "The Playbook"))
    checks["playbook_5_to_8"] = PASS if 5 <= playbook <= 8 else FAIL

    checks["benchmarks_have_turns"] = PASS if len(benchmark_turns(plan)) >= 3 else FAIL
    checks["what_goes_wrong_2plus"] = (
        PASS if _bullets(section(plan, "What Goes Wrong")) >= 2 else FAIL
    )

    dedications = section(plan, "Dedications").lower()
    checks["dedications_cover_ages"] = (
        PASS if "golden" in dedications and ("normal" in dedications or "dark" in dedications)
        else FAIL
    )

    if facts.available():
        states = {e["name"] for e in facts.city_states()}
        cs_text = section(plan, "City-States & Envoys")
        named = {s for s in states if re.search(rf"\b{re.escape(s)}\b", cs_text)}
        checks["city_states_named_2plus"] = PASS if len(named) >= 2 else FAIL

        promotions = {
            p["name"] for kit in facts.governor_kits() for p in kit.get("promotions", [])
        }
        gov_text = section(plan, "Governors")
        promo_hits = {p for p in promotions if re.search(rf"\b{re.escape(p)}\b", gov_text)}
        checks["governor_promotions_named"] = PASS if promo_hits else FAIL

        unverified = facts.unverified_names(plan)
        checks["no_unverified_names"] = PASS if not unverified else FAIL
    else:
        for name in ("city_states_named_2plus", "governor_promotions_named",
                     "no_unverified_names"):
            checks[name] = SKIP
        unverified = []

    if tree.for_ruleset(ruleset):
        tree_issues = tree.path_issues(plan, ruleset)
        checks["paths_follow_the_tree"] = PASS if not tree_issues else FAIL
    else:
        checks["paths_follow_the_tree"] = SKIP
        tree_issues = []

    # Opening with one civ and playing another ("Korea is the clean pick… instead, take
    # Germany") reads as indecision and used to mislabel the build.
    opener = re.search(r"\*\*(.+?)\*\*", section(plan, "Civ & Leader"))
    first = match_civ(opener.group(1)) if opener else None
    played = civ_from_plan(plan)
    checks["no_switched_pick"] = SKIP if not (first and played) else (
        PASS if first == played else FAIL
    )

    tripped = [
        {"id": wid, "note": note, "text": m.group(0)[:120]}
        for wid, pattern, note in KNOWN_WRONG
        for m in [re.search(pattern, plan)]
        if m
    ]
    checks["no_known_wrong_claims"] = PASS if not tripped else FAIL

    return {
        "checks": checks,
        "words": words,
        "playbook_bullets": playbook,
        "benchmark_turns": benchmark_turns(plan),
        "unverified": unverified,
        "tree_issues": tree_issues,
        "known_wrong": tripped,
    }


def speed_scaling(results: list[dict], standard_id: str, marathon_id: str) -> str:
    """Suite-level: Marathon benchmarks should sit well above Standard ones.

    Marathon is three times as long as Standard; a ratio of medians under 2 means the
    coach quoted Standard turns regardless of the configured speed.
    """
    def turns(brief_id: str) -> list[int]:
        return [t for r in results if r["brief"] == brief_id and r.get("score")
                for t in r["score"]["benchmark_turns"]]

    standard, marathon = turns(standard_id), turns(marathon_id)
    if not standard or not marathon:
        return SKIP
    return PASS if median(marathon) >= 2 * median(standard) else FAIL
