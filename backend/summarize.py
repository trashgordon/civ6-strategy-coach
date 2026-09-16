"""Pulling structured bits back out of a generated plan.

The compare view wants a side-by-side table with "key techs/wonders" per build. The plan
is markdown prose, so this is best-effort text extraction, not parsing — it reads the
relevant "##" sections and lifts the emphasized terms the coach named. When it finds
nothing it returns an empty list and the table shows a dash, which is honest; the full
plan is always one click away.
"""

import re

# Section header keyword -> how many terms are worth showing from it.
_TECH_SECTIONS = ("tech path", "civic path")
_WONDER_HINT = re.compile(r"wonder", re.IGNORECASE)


def sections(plan: str) -> dict[str, str]:
    """Split a plan into {lowercased header: body}."""
    if not plan:
        return {}
    found: dict[str, str] = {}
    matches = list(re.finditer(r"^#{2,3}\s+(.+?)\s*$", plan, flags=re.MULTILINE))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(plan)
        header = match.group(1).strip().lower()
        # Headers often arrive numbered ("## 2. Tech path").
        header = re.sub(r"^\d+[.)]\s*", "", header)
        found[header] = plan[match.end() : end].strip()
    return found


# A coach who says "skip Iron Working" still bolds Iron Working. Lines that tell you
# *not* to do something must not feed a column headed "key techs".
_NEGATED_LINE = re.compile(
    r"\b(?:skip|skipping|avoid|ignore|never|don't|do not|no need|not worth|forget"
    r"|leave\s+\w+\s+alone|don't bother|nowhere)\b",
    re.IGNORECASE,
)


def _emphasized(text: str) -> list[str]:
    """Bolded terms first; they're how the coach marks the things that matter."""
    terms: list[str] = []
    for line in text.splitlines():
        if _NEGATED_LINE.search(line):
            continue
        terms.extend(t.strip(" .,;:—–-") for t in re.findall(r"\*\*(.+?)\*\*", line))
    return [t for t in terms if t and len(t) <= 40]


def _bullet_leads(text: str) -> list[str]:
    """Fallback: the first clause of each bullet."""
    leads = []
    for line in text.splitlines():
        line = line.strip()
        if not re.match(r"^[-*]\s+|^\d+[.)]\s+", line):
            continue
        if _NEGATED_LINE.search(line):
            continue
        line = re.sub(r"^[-*]\s+|^\d+[.)]\s+", "", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        lead = re.split(r"\s*[—–:(]\s*|\s+-\s+", line, maxsplit=1)[0].strip(" .,;")
        if lead and len(lead) <= 40:
            leads.append(lead)
    return leads


def _dedupe(terms: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    kept: list[str] = []
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        kept.append(term)
        if len(kept) >= limit:
            break
    return kept


def key_techs_and_wonders(plan: str, limit: int = 6) -> list[str]:
    """The headline techs, civics and wonders named in a plan."""
    parsed = sections(plan)
    if not parsed:
        return []

    harvested: list[str] = []
    for header, body in parsed.items():
        if any(keyword in header for keyword in _TECH_SECTIONS):
            harvested.extend(_emphasized(body) or _bullet_leads(body))

    # Wonders get named all over the plan, so sweep any section that mentions them.
    for header, body in parsed.items():
        if _WONDER_HINT.search(header) or _WONDER_HINT.search(body):
            harvested.extend(term for term in _emphasized(body) if term not in harvested)

    return _dedupe(harvested, limit)


def compare_row(build: dict) -> dict:
    """One row of the compare table."""
    return {
        "id": build.get("id"),
        "title": build.get("title") or "Untitled",
        "civ": build.get("civ") or "",
        "primary_focus": build.get("primary_focus") or "",
        "posture": build.get("posture") or "",
        "city_philosophy": build.get("city_philosophy") or "",
        "ruleset": build.get("ruleset") or "",
        "difficulty": build.get("difficulty") or "",
        "map_type": build.get("map_type") or "",
        "key_terms": key_techs_and_wonders(build.get("generated_plan") or ""),
    }
