"""Canonical Civ VI names the backend needs to recognise in generated text.

Mirrors the lists in `frontend/src/data.js` — keep the two in step, the same way
`prompts.MODE_LABELS` mirrors `MODES` there.
"""

CIVS = (
    "America", "Arabia", "Australia", "Aztec", "Babylon", "Brazil", "Byzantium", "Canada",
    "China", "Cree", "Egypt", "England", "Ethiopia", "France", "Gaul", "Georgia",
    "Germany", "Gran Colombia", "Greece", "Hungary", "Inca", "India", "Indonesia", "Japan",
    "Khmer", "Kongo", "Korea", "Macedon", "Mali", "Maori", "Mapuche", "Maya",
    "Mongolia", "Netherlands", "Norway", "Ottoman", "Persia", "Phoenicia", "Poland", "Rome",
    "Russia", "Scotland", "Scythia", "Spain", "Sumeria", "Sweden", "Vietnam", "Zulu",
)

# The coach writes "Māori"; the dropdown says "Maori". Match either.
_ALIASES = {
    "maori": "Maori",
    "māori": "Maori",
    "gran colombia": "Gran Colombia",
    "the netherlands": "Netherlands",
    "the ottomans": "Ottoman",
    "ottomans": "Ottoman",
    "roman": "Rome",
}

_LOOKUP = {civ.lower(): civ for civ in CIVS}
_LOOKUP.update(_ALIASES)


def match_civ(text: str) -> str | None:
    """Return the canonical civ named anywhere in `text`, or None.

    Longest name first, so "Gran Colombia" isn't shadowed by a shorter match.
    """
    if not text:
        return None
    lowered = text.lower()
    for name in sorted(_LOOKUP, key=len, reverse=True):
        if name in lowered:
            return _LOOKUP[name]
    return None
