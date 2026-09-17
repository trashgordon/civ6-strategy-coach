"""Grounding the coach in the real game data.

Two jobs, both no-ops when `data/facts/` is empty (nobody has to own the game, or run
the extractor, for the app to work):

1. `prompt_block()` hands the model closed sets of real names, so it picks rather than
   recalls.
2. `unverified_names()` checks the finished plan and reports any name that isn't in the
   game data, so a fabrication that slips through is visible instead of silent.

Run `python -m backend.extract_gamedata` to populate it.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from .extract_gamedata import facts_dir
from .gamedata import CIVS

# Injected into the prompt. Chosen for the sections the coach actually writes, and
# trimmed because every name costs input tokens on every generation.
INJECT_CATEGORIES = (
    ("dedications", "Golden Age dedications"),
    ("governments", "Governments"),
    ("governors", "Governors"),
    ("technologies", "Technologies"),
    ("civics", "Civics"),
    ("wonders", "Wonders"),
    ("districts", "Districts"),
    ("policy_cards", "Policy cards"),
    ("beliefs", "Religious beliefs"),
)

# Checked against, but not injected — too many names to be worth the tokens, while still
# worth recognising so validation doesn't cry wolf over a unit or a Great Person.
_VALIDATE_ONLY = (
    "buildings", "improvements", "units", "resources", "civilizations", "leaders",
    "eras", "yields", "great_people", "projects", "features", "terrains",
    "governor_promotions", "religions", "abilities", "belief_classes",
)

# Vocabulary the coach bolds that is real language but not a game entity to look up.
_ALLOWED = {
    "tall", "wide", "turn", "turns", "early", "mid", "late", "mid-game", "late-game",
    "early-game", "endgame", "always", "never", "priority", "key", "note", "warning",
    "playbook", "capital", "city", "cities", "settler", "settlers", "builder",
    "builders", "war", "peace", "loyalty", "amenities", "housing", "adjacency",
    "beeline", "corps", "army", "fleet", "armada", "pantheon", "religion",
    "government", "wonder", "district", "policy", "card", "golden age", "dark age",
    "heroic age", "normal age", "era score", "casus belli", "suzerain", "suzerainty",
    "city-state", "city-states", "great person", "great people", "victory",
    "science victory", "culture victory", "domination victory", "religious victory",
    "diplomatic victory", "tourism", "great work", "theming bonus",
    # The six city-state categories are fixed game vocabulary — a plan says "ignore
    # Militaristic city-states" whether or not one is in the injected list.
    "cultural", "industrial", "militaristic", "religious", "scientific", "trade",
    "cultural city-state", "industrial city-state", "militaristic city-state",
    "religious city-state", "scientific city-state", "trade city-state",
}


@lru_cache(maxsize=1)
def city_states() -> tuple[dict[str, str], ...]:
    """Every city-state with its category and suzerain bonus."""
    directory = facts_dir()
    path = directory / "city_states.json"
    if not path.is_file():
        return ()
    try:
        entries = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return ()
    return tuple(
        e for e in entries
        if isinstance(e, dict) and e.get("name") and e.get("bonus")
    )


@lru_cache(maxsize=1)
def _load() -> dict[str, tuple[str, ...]]:
    directory = facts_dir()
    if not directory.is_dir():
        return {}
    loaded: dict[str, tuple[str, ...]] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            values = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(values, list):
            # city_states is a list of objects, handled by city_states() instead.
            loaded[path.stem] = tuple(
                str(v) for v in values if v and not isinstance(v, dict)
            )
    return loaded


def reload() -> None:
    """Forget the cache — used by tests and after re-running the extractor."""
    _load.cache_clear()
    _known_names.cache_clear()
    _proper_nouns.cache_clear()
    city_states.cache_clear()


def available() -> bool:
    return bool(_load())


def summary() -> dict[str, int]:
    return {name: len(values) for name, values in _load().items()}


def _variants(term: str) -> set[str]:
    """Every spelling of `term` worth matching on.

    The coach and the game disagree in small, predictable ways: "Games & Recreation" vs
    "Games and Recreation", "Enlightenment" vs "The Enlightenment", "Classical" vs
    "Classical Era", "Great Scientists" vs "Great Scientist", "Renaissance+".
    """
    base = term.strip().lower()
    base = base.rstrip("+")
    base = re.sub(r"[,\.]", "", base)
    base = base.replace("&", " and ")
    base = re.sub(r"\s+", " ", base).strip()

    forms = {base}
    for form in list(forms):
        if form.startswith("the "):
            forms.add(form[4:])
        else:
            forms.add(f"the {form}")
        # Era names appear both ways round.
        if form.endswith(" era"):
            forms.add(form[: -len(" era")])
        else:
            forms.add(f"{form} era")
        # Plurals, in both directions.
        if form.endswith("s") and len(form) > 3:
            forms.add(form[:-1])
        else:
            forms.add(f"{form}s")
    return forms


@lru_cache(maxsize=1)
def _known_names() -> frozenset[str]:
    names: set[str] = set()
    for word in _ALLOWED:
        names |= _variants(word)
    data = _load()
    for category in [c for c, _ in INJECT_CATEGORIES] + list(_VALIDATE_ONLY):
        for value in data.get(category, ()):
            names |= _variants(value)
    for entry in city_states():
        names |= _variants(entry["name"])
        # "Ignore Militaristic city-states" — the category is vocabulary, not a name.
        names |= _variants(entry["category"])
        names |= _variants(f"{entry['category']} city-state")
    return frozenset(names)


def prompt_block(max_names_per_category: int = 400) -> str:
    """Closed sets of real names for the system prompt. Empty string when unavailable."""
    data = _load()
    if not data:
        return ""

    lines = [
        "These are the real names from the installed game. When you name a tech, civic,",
        "wonder, district, policy card, belief, governor, government or Golden Age",
        "dedication, use one of these exactly. If what you want isn't listed, say so",
        "rather than inventing a name.",
        "",
    ]
    for category, label in INJECT_CATEGORIES:
        values = data.get(category, ())
        if not values:
            continue
        shown = values[:max_names_per_category]
        lines.append(f"{label}: " + "; ".join(shown))
        lines.append("")

    states = city_states()
    if states:
        lines.append(
            "City-states and their suzerain bonuses. Name real ones with the bonus they "
            "actually give; don't describe a bonus you can't find here."
        )
        by_category: dict[str, list[str]] = {}
        for entry in states:
            by_category.setdefault(entry["category"], []).append(
                f"{entry['name']} ({entry['bonus']})"
            )
        for category in sorted(by_category):
            lines.append(f"{category}: " + "; ".join(by_category[category]))
        lines.append("")

    return "\n".join(lines).strip()


# People and places get written loosely: "Kupe of Maori", "Kongo's Mvemba", "Eleanor of
# Aquitaine" when the data disambiguates it as "Eleanor of Aquitaine (England)". Matching
# these by containment rather than equality is safe, because it can only ever suppress a
# flag that was already raised.
_PEOPLE_AND_PLACES = ("leaders", "civilizations", "great_people")
_MIN_CONTAINMENT = 4  # "Ur" would otherwise match almost anything


@lru_cache(maxsize=1)
def _proper_nouns() -> tuple[str, ...]:
    data = _load()
    names = {c.lower() for c in CIVS}
    for category in _PEOPLE_AND_PLACES:
        names.update(v.lower() for v in data.get(category, ()))
    names.update(e["name"].lower() for e in city_states())
    return tuple(n for n in names if len(n) >= _MIN_CONTAINMENT)


def _names_a_real_person_or_place(term: str) -> bool:
    """True when `term` overlaps a known leader, civ or Great Person either way round."""
    lowered = re.sub(r"[^a-z0-9 ]", " ", term.lower())
    lowered = re.sub(r"\s+", " ", lowered).strip()
    if not lowered:
        return False
    for known in _proper_nouns():
        if known in lowered or lowered in known:
            return True
    return False


# The recommendation section is prose about a pick — it names rival civs and leaders in
# passing, which isn't the kind of assertion worth checking. Fabricated card and
# dedication names, the actual failure mode, live in the sections after it.
_CIV_LEADER_SECTION = re.compile(
    r"^##\s*Civ\s*&\s*Leader.*?(?=^##|\Z)", re.MULTILINE | re.DOTALL
)


# The coach's own emphasis is the signal for "this is a name I'm asserting".
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CHAIN = re.compile(r"\s*(?:→|->|➜|»|/)\s*")
_NAME_PARTICLES = {"and", "of", "the", "&"}


def _looks_like_an_entity(term: str) -> bool:
    """Title Case and short enough to be a name rather than a phrase."""
    words = term.split()
    if not words or len(words) > 5:
        return False
    if not words[0][:1].isupper():
        return False
    for word in words[1:]:
        bare = word.strip(",.;:&'")
        if not bare or bare.lower() in _NAME_PARTICLES:
            continue
        if not bare[:1].isupper():
            return False
    return True


def unverified_names(plan: str) -> list[str]:
    """Bolded names in `plan` that don't appear anywhere in the game data.

    Empty when no facts are installed — silence is the honest answer there, rather than
    flagging everything as unverified.
    """
    if not plan or not available():
        return []

    known = _known_names()
    flagged: list[str] = []
    seen: set[str] = set()

    scanned = _CIV_LEADER_SECTION.sub("", plan)
    for bold in _BOLD.findall(scanned):
        for piece in _CHAIN.split(bold):
            for term in _checkable_terms(piece, known):
                key = term.lower()
                if key in seen:
                    continue
                seen.add(key)
                flagged.append(term)
    return flagged


def _recognised(term: str, known: frozenset[str]) -> bool:
    if _variants(term) & known:
        return True
    # A number or a bare era reference isn't a claim about a game entity.
    if any(ch.isdigit() for ch in term):
        return True
    return _names_a_real_person_or_place(term)


def _checkable_terms(piece: str, known: frozenset[str]) -> list[str]:
    """The terms in one bolded run that are genuinely unrecognised.

    A run is tried whole first, so "Pen, Brush, and Voice" matches as the single name it
    is. Only if that fails is it treated as a comma-separated list — "Irrigation, Mining,
    Bronze Working" is three techs — and each item checked on its own. That way a
    fabrication hiding inside a list is still caught, without splitting real names apart.
    """
    term = piece.strip(" .,;:—–-*()").strip()
    if not term:
        return []

    if _looks_like_an_entity(term):
        if _recognised(term, known):
            return []
        if "," not in term:
            return [term]
    elif "," not in term:
        return []

    parts = []
    for raw in term.split(","):
        item = re.sub(r"^\s*and\s+", "", raw.strip(), flags=re.IGNORECASE)
        item = item.strip(" .;:—–-*()")
        if item:
            parts.append(item)
    if len(parts) < 2 or not all(_looks_like_an_entity(p) for p in parts):
        # Not a list of names after all — report the whole run if it looked like one.
        return [term] if _looks_like_an_entity(term) else []

    return [p for p in parts if not _recognised(p, known)]
