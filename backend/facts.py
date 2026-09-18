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
import unicodedata
from functools import lru_cache
from pathlib import Path

from .extract_gamedata import facts_dir
from .gamedata import CIVS

# Injected into the prompt. Chosen for the sections the coach actually writes, and
# trimmed because every name costs input tokens on every generation.
INJECT_CATEGORIES = (
    # "dedications" is injected separately, with its per-age bonuses.
    ("governments", "Governments"),
    ("technologies", "Technologies"),
    ("civics", "Civics"),
    ("wonders", "Wonders"),
    ("districts", "Districts"),
    ("policy_cards", "Policy cards"),
    ("beliefs", "Religious beliefs"),
    ("alliances", "Alliance types"),
)

# Checked against, but not injected — too many names to be worth the tokens, while still
# worth recognising so validation doesn't cry wolf over a unit or a Great Person.
_VALIDATE_ONLY = (
    "buildings", "improvements", "units", "resources", "civilizations", "leaders",
    "eras", "yields", "great_people", "projects", "features", "terrains",
    "religions", "abilities", "belief_classes", "governors", "governor_promotions",
    # Injected separately with their per-age bonuses, but the plain name list is still
    # what validation checks against.
    "dedications",
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
    # Age labels — "**Normal/Dark Age:**" splits into a bare "Normal".
    "golden", "normal", "dark", "heroic", "age", "ages",
    # Imperatives the coach bolds to open a bullet.
    "ignore", "skip", "rush", "grab", "take", "build", "buy", "watch", "stop",
    "pivot", "avoid", "prioritise", "prioritize", "beeline", "settle", "expand",
    "tech", "techs", "first", "next", "then", "finally", "result", "fix",
}


@lru_cache(maxsize=1)
def effects() -> dict[str, str]:
    """{name: what it actually does}, from the game's own description text.

    This is the difference between the coach knowing "Corvée" is a real card and
    knowing it is +15% production toward ancient and classical wonders rather than,
    as it kept asserting, something to do with settlers.
    """
    path = facts_dir() / "effects.json"
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


@lru_cache(maxsize=1)
def governor_kits() -> tuple[dict, ...]:
    """Each governor with the promotions that belong to them."""
    path = facts_dir() / "governor_kits.json"
    if not path.is_file():
        return ()
    try:
        entries = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return ()
    return tuple(e for e in entries if isinstance(e, dict) and e.get("governor"))


@lru_cache(maxsize=1)
def dedication_bonuses() -> tuple[dict[str, str], ...]:
    """Dedications with their era range and all three age bonuses."""
    path = facts_dir() / "dedication_bonuses.json"
    if not path.is_file():
        return ()
    try:
        entries = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return ()
    return tuple(e for e in entries if isinstance(e, dict) and e.get("name"))


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
        if path.stem == "effects":
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
    _leading_words.cache_clear()
    city_states.cache_clear()
    effects.cache_clear()
    dedication_bonuses.cache_clear()
    governor_kits.cache_clear()


def available() -> bool:
    return bool(_load())


def summary() -> dict[str, int]:
    """How many of each fact group is loaded, for /api/meta.

    city_states is counted separately: _load() strips the dict entries, so reading the
    count from there reports 0 for a group that is in fact populated.
    """
    counts = {name: len(values) for name, values in _load().items()}
    states = city_states()
    if states:
        counts["city_states"] = len(states)
    else:
        counts.pop("city_states", None)
    bonuses = dedication_bonuses()
    if bonuses:
        counts["dedication_bonuses"] = len(bonuses)
    kits = governor_kits()
    if kits:
        counts["governor_kits"] = len(kits)
    return counts


def _fold(text: str) -> str:
    """Lowercase and strip diacritics, so "Māori" and "Maori" are the same name.

    Civ VI is full of accented names and plans spell them either way. Replacing the
    accented character rather than folding it turned "Māori" into "m ori", which matched
    nothing.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _variants(term: str) -> set[str]:
    """Every spelling of `term` worth matching on.

    The coach and the game disagree in small, predictable ways: "Games & Recreation" vs
    "Games and Recreation", "Enlightenment" vs "The Enlightenment", "Classical" vs
    "Classical Era", "Great Scientists" vs "Great Scientist", "Renaissance+".
    """
    base = _fold(term.strip())
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
    for civ in CIVS:
        names |= _variants(civ)
    for belief_class in data.get("belief_classes", ()):
        names |= _variants(f"{belief_class} belief")
    for kit in governor_kits():
        names |= _variants(kit["governor"])
        for promo in kit.get("promotions", []):
            names |= _variants(promo["name"])
    for entry in dedication_bonuses():
        names |= _variants(entry["name"])
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

    known_effects = effects()
    lines = [
        "These are the real names from the installed game, with what they actually do",
        "where the game defines it. Use these names exactly, and describe an effect only",
        "as it is written here — don't recall it from memory and don't invent a name. If",
        "what you want isn't listed, say so.",
        "",
    ]
    for category, label in INJECT_CATEGORIES:
        values = data.get(category, ())
        if not values:
            continue
        shown = values[:max_names_per_category]
        lines.append(f"{label}:")
        for value in shown:
            effect = known_effects.get(value)
            lines.append(f"- {value}: {effect}" if effect else f"- {value}")
        lines.append("")

    abilities = data.get("abilities", ())
    described = [(a, known_effects[a]) for a in abilities if a in known_effects]
    if described:
        lines.append("Civ and leader abilities:")
        for name, effect in described:
            lines.append(f"- {name}: {effect}")
        lines.append("")

    kits = governor_kits()
    if kits:
        lines.append(
            "Governors and the promotions that belong to each. A promotion is only "
            "available to its own governor, so name the governor and the promotion "
            "together."
        )
        for kit in kits:
            lines.append(f"- {kit['governor']}")
            for promo in kit.get("promotions", []):
                effect = promo.get("effect")
                lines.append(
                    f"    {promo['name']}: {effect}" if effect else f"    {promo['name']}"
                )
        lines.append("")

    dedications = dedication_bonuses()
    if dedications:
        lines.append(
            "Dedications. You pick one at every era change, not only for a Golden Age: "
            "in a Golden Age it gives the effect below, and in a Normal or Dark Age it "
            "instead earns era score toward the next one. Each is only offered in the "
            "eras shown."
        )
        for entry in dedications:
            lines.append(f"- {entry['name']} ({entry.get('eras') or 'any era'})")
            if entry.get("golden"):
                lines.append(f"    golden age: {entry['golden']}")
            if entry.get("normal"):
                lines.append(f"    normal or dark age: {entry['normal']}")
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


@lru_cache(maxsize=1)
def _leading_words() -> frozenset[str]:
    """First words of real multi-word names: "horseback" from "Horseback Riding".

    A second mention often shortens the name — "Currency → Horseback". That's a
    truncation, not an invention, and flagging it as "not found in your game data"
    would cry wolf about a real tech.
    """
    words: set[str] = set()
    data = _load()
    for category in [c for c, _ in INJECT_CATEGORIES] + list(_VALIDATE_ONLY):
        for value in data.get(category, ()):
            parts = _fold(value).split()
            if len(parts) > 1 and len(parts[0]) >= 5:
                words.add(parts[0])
    return frozenset(words)


# People and places get written loosely: "Kupe of Maori", "Kongo's Mvemba", "Eleanor of
# Aquitaine" when the data disambiguates it as "Eleanor of Aquitaine (England)". Matching
# these by containment rather than equality is safe, because it can only ever suppress a
# flag that was already raised.
_PEOPLE_AND_PLACES = ("leaders", "civilizations", "great_people")
_MIN_CONTAINMENT = 4  # "Ur" would otherwise match almost anything


@lru_cache(maxsize=1)
def _proper_nouns() -> tuple[str, ...]:
    data = _load()
    names = {_fold(c) for c in CIVS}
    for category in _PEOPLE_AND_PLACES:
        names.update(_fold(v) for v in data.get(category, ()))
    names.update(_fold(e["name"]) for e in city_states())
    return tuple(n for n in names if len(n) >= _MIN_CONTAINMENT)


def _names_a_real_person_or_place(term: str) -> bool:
    """True when `term` overlaps a known leader, civ or Great Person either way round."""
    lowered = re.sub(r"[^a-z0-9 ]", " ", _fold(term))
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
_CHAIN = re.compile(r"\s*(?:→|->|➜|»)\s*")
# Commas and slashes both introduce lists: "Irrigation, Mining", "Amsterdam/Venice".
_LIST_SEPARATOR = re.compile(r"\s*[,/–]\s*")
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


# "Political Philosophy's Monarchic Legacy", "Kongo's Mvemba" — a possessive points at
# a real thing on one side of the apostrophe.
_POSSESSIVE = re.compile(r"['\u2019]s\s+")


def _recognised(term: str, known: frozenset[str], allow_containment: bool = True) -> bool:
    if _variants(term) & known:
        return True
    # A lone word that opens a real multi-word name is a shortened mention.
    if " " not in term.strip() and _fold(term.strip()) in _leading_words():
        return True
    if _POSSESSIVE.search(term):
        # Either side of the apostrophe may be the real name.
        for part in _POSSESSIVE.split(term, maxsplit=1):
            part = part.strip(" .,;:—–-")
            if part and _variants(part) & known:
                return True
    # A number or a bare era reference isn't a claim about a game entity.
    if any(ch.isdigit() for ch in term):
        return True
    # Containment is for loose phrasing of one name ("Kongo's Mvemba"). Applied to a
    # list it would let a real entry vouch for a fabricated neighbour, so
    # "Amsterdam/Genevia" would pass on the strength of Amsterdam alone.
    return allow_containment and _names_a_real_person_or_place(term)


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

    has_list = bool(_LIST_SEPARATOR.search(term))
    if _looks_like_an_entity(term):
        if _recognised(term, known, allow_containment=not has_list):
            return []
        if not has_list:
            return [term]
    elif not has_list:
        return []

    parts = []
    for raw in _LIST_SEPARATOR.split(term):
        item = re.sub(r"^\s*and\s+", "", raw.strip(), flags=re.IGNORECASE)
        item = item.strip(" .;:—–-*()")
        if item:
            parts.append(item)
    if len(parts) < 2 or not all(_looks_like_an_entity(p) for p in parts):
        # Not a list of names after all — report the whole run if it looked like one.
        return [term] if _looks_like_an_entity(term) else []

    return [p for p in parts if not _recognised(p, known)]
