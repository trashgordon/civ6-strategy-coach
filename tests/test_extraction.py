"""Pulling structured facts back out of a generated plan.

Both of these are best-effort text extraction over model prose, so the cases here are
taken from real plans the app actually produced.
"""

import pytest

from backend import gamedata, summarize, titles


# --------------------------------------------------------------------------- civs


@pytest.mark.parametrize(
    "text, expected",
    [
        # Civ first, leader second.
        ("Rome — Trajan", "Rome"),
        ("Korea — Seondeok", "Korea"),
        ("Rome (Trajan)", "Rome"),
        # Leader first, civ second — taking the first token would give "Kupe".
        ("Kupe / Māori", "Maori"),
        ("Wilhelmina of the Netherlands", "Netherlands"),
        # Two-word civ isn't shadowed by a shorter match.
        ("Gran Colombia", "Gran Colombia"),
        ("nothing recognisable here", None),
        ("", None),
    ],
)
def test_match_civ(text, expected):
    assert gamedata.match_civ(text) == expected


def test_title_reads_a_civ_whichever_side_of_the_separator_it_is_on():
    plan = "## Civ & Leader\n**Kupe / Māori**\nGreat culture engine."
    assert titles.civ_from_plan(plan) == "Maori"


def test_title_reads_a_civ_out_of_the_header_too():
    """Plans written before the prompt pinned headers put the pick in the header."""
    plan = "## Civ & Leader: Rome (Trajan)\n\nPangaea + wide + domination."
    assert titles.civ_from_plan(plan) == "Rome"
    assert titles.suggest_title(
        civ="", city_philosophy="Wide", primary_focus="Domination",
        posture="Aggressive / militaristic", plan=plan,
    ) == "Rome — Domination, Wide, Aggressive"


def test_an_unknown_civ_falls_back_to_the_first_segment():
    """A mod or a civ the list doesn't carry still gets a usable title."""
    plan = "## Civ & Leader\n**Atlantis — Poseidon**\nNot a real civ."
    assert titles.civ_from_plan(plan) == "Atlantis"


# ----------------------------------------------------------------- key term picking


def test_arrow_chains_are_split_into_individual_techs():
    """A bolded beeline is one run; unsplit it exceeds the length cap and is dropped."""
    plan = "## Tech Path\n**Sailing → Pottery → Irrigation → Writing → Masonry**\n"
    assert summarize.key_techs_and_wonders(plan) == [
        "Sailing", "Pottery", "Irrigation", "Writing", "Masonry",
    ]


def test_prose_fragments_are_not_mistaken_for_techs():
    """Real regressions: "Key pivots" and "policy card gold" were showing up."""
    plan = """## Tech Path
**Key pivots:**
- **Education** for Universities
- **Medieval Faires** → policy card gold
"""
    terms = summarize.key_techs_and_wonders(plan)
    assert "Key pivots" not in terms
    assert "policy card gold" not in terms
    assert terms == ["Education", "Medieval Faires"]


def test_leading_connectors_are_stripped():
    plan = "## Tech Path\n- **Then Construction** for walls\n- Beeline **Education**\n"
    assert summarize.key_techs_and_wonders(plan) == ["Construction", "Education"]


def test_multi_word_names_with_lowercase_particles_survive():
    """"Defender of the Faith" and "Games & Recreation" are real names."""
    plan = "## Civic Path\n- **Games & Recreation**\n- **Defender of the Faith**\n"
    assert summarize.key_techs_and_wonders(plan) == [
        "Games & Recreation", "Defender of the Faith",
    ]


def test_skipped_techs_still_excluded():
    plan = """## Tech Path
- **Writing** first
- Skip **Iron Working** entirely — you don't need it
"""
    assert summarize.key_techs_and_wonders(plan) == ["Writing"]


def test_bullet_leads_are_the_fallback_when_nothing_is_bolded():
    plan = "## Tech Path\n- Bronze Working for Legions\n- Iron Working next\n"
    assert summarize.key_techs_and_wonders(plan) == ["Bronze Working", "Iron Working"]
