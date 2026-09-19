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


SWITCHED = """## Civ & Leader

**Korea (Seondeok)** is the clean pick for science. But you said "production-heavy",
so instead, take **Germany (Frederick Barbarossa)**: Hansa districts pump out production.

## Tech Path
- **Apprenticeship** for Hansa

## City & District Layout
Every core city gets a Hansa next to its Commercial Hub.
"""


def test_a_pick_the_coach_switched_away_from_is_not_the_civ(no_tree):
    assert titles.civ_from_plan(SWITCHED) == "Germany"


def test_the_played_civ_is_the_one_whose_uniques_the_plan_uses(tree_with_uniques):
    # No pivot phrase to go on — only the uniques give it away.
    plan = SWITCHED.replace("so instead, take", "and")
    assert titles.civ_from_plan(plan) == "Germany"


def test_a_mentioned_alternative_does_not_steal_the_pick(tree_with_uniques):
    plan = SWITCHED.replace(
        '**Korea (Seondeok)** is the clean pick for science. But you said "production-heavy",\nso instead, take **Germany (Frederick Barbarossa)**',
        "**Germany (Frederick Barbarossa)** is the pick. **Korea** is the runner-up",
    )
    assert titles.civ_from_plan(plan) == "Germany"
    no_hansa = plan.split("## Tech Path")[0]
    assert titles.civ_from_plan(no_hansa) == "Germany"   # nothing to go on: the first pick stands


@pytest.fixture
def no_tree(tmp_path, monkeypatch):
    from backend import facts
    monkeypatch.setattr(facts, "facts_dir", lambda: tmp_path / "nothing")
    facts.reload()
    yield
    facts.reload()


@pytest.fixture
def tree_with_uniques(tmp_path, monkeypatch):
    import json
    from backend import facts
    (tmp_path / "tree.json").write_text(json.dumps({"Gathering Storm": {
        "technologies": {}, "civics": {},
        "unlocks": [
            {"name": "Hansa", "kind": "district", "by": "Apprenticeship", "tree": "technology", "civ": "Germany"},
            {"name": "Seowon", "kind": "district", "by": "Writing", "tree": "technology", "civ": "Korea"},
        ],
    }}))
    monkeypatch.setattr(facts, "facts_dir", lambda: tmp_path)
    facts.reload()
    yield
    facts.reload()


def test_a_scratched_first_pick_is_not_the_civ(no_tree):
    plan = ("## Civ & Leader\n\n**Kupe / Māori** is not a religion pick — scratch that instinct. "
            "For a religion build, go **Saladin of Arabia**.\n\n## Tech Path\n- x\n")
    assert titles.civ_from_plan(plan) == "Arabia"


@pytest.mark.parametrize("offer", [
    "Runner-up: **Greece (Pericles)** if you want the textbook route.",
    "If you'd rather go wide, take **Greece** instead.",
    "Alternatively, go **Greece** for a faster start.",
])
def test_an_offered_runner_up_is_not_a_switch(no_tree, offer):
    plan = f"## Civ & Leader\n\n**Georgia (Tamar)** fits tall culture. {offer}\n\n## Tech Path\n- x\n"
    assert titles.civ_from_plan(plan) == "Georgia"
