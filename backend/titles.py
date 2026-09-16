"""Auto-suggested titles for saved builds.

Derived from the build itself rather than a second model call — a saved build shouldn't
cost two requests, and the title is editable anyway.
"""

import re

from .gamedata import match_civ

NO_PREFERENCE = "No preference"


def _meaningful(value: str | None) -> str:
    value = (value or "").strip()
    return "" if value == NO_PREFERENCE else value


def civ_from_plan(plan: str) -> str:
    """Pull the recommended civ out of the plan's first section, if it's findable.

    The prompt asks for "## Civ & Leader recommendation" first, and the coach reliably
    leads that section with the pick. We take the first bold run, or failing that the
    first line of prose, and keep the part before any dash separating civ from leader.
    """
    if not plan:
        return ""

    body = plan
    first_header = re.search(r"^##\s+(.*)$", plan, flags=re.MULTILINE)
    if first_header:
        # Older plans (before the prompt pinned the headers) sometimes put the pick in
        # the header itself — "## Civ & Leader: Rome (Trajan)".
        from_header = match_civ(first_header.group(1))
        if from_header:
            return from_header
        body = plan[first_header.end() :]
    # Stop at the next section so we never read the tech path by mistake.
    next_header = re.search(r"^##\s+", body, flags=re.MULTILINE)
    if next_header:
        body = body[: next_header.start()]

    bold = re.search(r"\*\*(.+?)\*\*", body)
    candidate = bold.group(1) if bold else ""
    if not candidate:
        for line in body.splitlines():
            line = line.strip().lstrip("-*# ").strip()
            if line:
                candidate = line
                break

    # Match a known civ anywhere in the candidate rather than assuming which side of the
    # separator it sits on: the coach writes both "Rome — Trajan" (civ first) and
    # "Kupe / Māori" (leader first), so taking the first token is wrong half the time.
    civ = match_civ(candidate)
    if civ:
        return civ

    # An unrecognised civ (a mod, or a name the list doesn't carry) falls back to the
    # first segment, which is right for the "Civ — Leader" shape.
    candidate = re.split(r"\s*[—–/\-:(]\s*", candidate, maxsplit=1)[0]
    candidate = candidate.strip(" *.,’'\"")
    # Anything long is prose, not a civ name.
    if not candidate or len(candidate) > 28:
        return ""
    return candidate


def suggest_title(
    *,
    civ: str,
    city_philosophy: str,
    primary_focus: str,
    posture: str,
    plan: str,
) -> str:
    """e.g. "Korea — Science, Tall" / "Coach's pick — Domination" / "Custom build"."""
    subject = _meaningful(civ) or civ_from_plan(plan) or "Coach's pick"

    descriptors = [
        _meaningful(primary_focus),
        _meaningful(city_philosophy),
        _shorten_posture(_meaningful(posture)),
    ]
    descriptors = [d for d in descriptors if d]

    if not descriptors:
        return subject
    return f"{subject} — {', '.join(descriptors)}"


def _shorten_posture(posture: str) -> str:
    """The posture labels are long for a title; keep the first word."""
    if not posture:
        return ""
    return posture.split("/")[0].strip()
