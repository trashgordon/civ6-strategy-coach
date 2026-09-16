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


# Connector words the coach opens a clause with — "Then Construction", "Beeline
# Education". The name is what follows.
_LEAD_CONNECTOR = re.compile(
    r"^(?:then|next|beeline|rush|grab|take|get|build|go|head|open|start|prioriti[sz]e"
    r"|straight to|follow with|pick up)\s+",
    re.IGNORECASE,
)

# Lowercase particles that legitimately appear inside a Civ VI name:
# "Games & Recreation", "Defender of the Faith", "Pen, Brush and Voice".
_NAME_PARTICLES = {"and", "of", "the", "&"}


def _looks_like_a_name(term: str) -> bool:
    """A tech, civic or wonder is Title Case. Prose fragments are not.

    "Political Philosophy" and "Defender of the Faith" pass; "Key pivots", "policy card
    gold" and "unlocks Great Writers" do not.
    """
    words = term.split()
    if not words or len(words) > 5:
        return False
    if not words[0][:1].isupper():
        return False
    for word in words[1:]:
        stripped = word.strip(",.;:&")
        if not stripped or stripped.lower() in _NAME_PARTICLES:
            continue
        if not stripped[:1].isupper():
            return False
    return True


def _leading_name(text: str) -> str:
    """The Title Case run at the start of a clause.

    "Bronze Working for Legions" -> "Bronze Working". Stops at the first lowercase word
    that isn't a particle joining a longer name.
    """
    kept: list[str] = []
    for word in text.split():
        bare = word.strip(",.;:&")
        if not bare:
            continue
        if bare[:1].isupper():
            kept.append(word)
            continue
        if bare.lower() in _NAME_PARTICLES and kept:
            kept.append(word)
            continue
        break
    # A trailing particle belongs to the prose that followed, not the name.
    while kept and kept[-1].strip(",.;:&").lower() in _NAME_PARTICLES:
        kept.pop()
    return " ".join(kept)


def _split_chain(term: str) -> list[str]:
    """A bolded beeline is one run: "Writing → Currency → Astrology". Split it.

    Without this, plan-length arrow chains blow past the length cap and are dropped
    whole, leaving the compare column empty.
    """
    parts = re.split(r"\s*(?:→|->|➜|»)\s*", term)
    return [part.strip(" .,;:—–-*") for part in parts if part.strip()]


def _candidates(text: str) -> list[str]:
    """Bolded names, arrow-chains expanded, prose fragments rejected."""
    terms: list[str] = []
    for line in text.splitlines():
        if _NEGATED_LINE.search(line):
            continue
        for bold in re.findall(r"\*\*(.+?)\*\*", line):
            for piece in _split_chain(bold):
                piece = _LEAD_CONNECTOR.sub("", piece).strip(" .,;:—–-")
                if piece and len(piece) <= 40 and _looks_like_a_name(piece):
                    terms.append(piece)
    return terms


def _bullet_leads(text: str) -> list[str]:
    """Fallback for plans that bold nothing: the leading name of each bullet."""
    leads = []
    for line in text.splitlines():
        line = line.strip()
        if not re.match(r"^[-*]\s+|^\d+[.)]\s+", line):
            continue
        if _NEGATED_LINE.search(line):
            continue
        line = re.sub(r"^[-*]\s+|^\d+[.)]\s+", "", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        lead = re.split(r"\s*[—–:(]\s*|\s+-\s+", line, maxsplit=1)[0]
        for piece in _split_chain(lead):
            piece = _LEAD_CONNECTOR.sub("", piece).strip(" .,;:")
            piece = _leading_name(piece)
            if piece and len(piece) <= 40 and _looks_like_a_name(piece):
                leads.append(piece)
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
            harvested.extend(_candidates(body) or _bullet_leads(body))

    # Wonders get named all over the plan, so sweep any section that mentions them.
    for header, body in parsed.items():
        if _WONDER_HINT.search(header) or _WONDER_HINT.search(body):
            harvested.extend(term for term in _candidates(body) if term not in harvested)

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
