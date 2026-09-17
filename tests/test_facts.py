"""Grounding the coach in the installed game's own data.

Everything here must degrade silently: plenty of users won't own the game, won't run the
extractor, or will be on a platform the extractor can't find an install on.
"""

import json

import pytest

from backend import facts, prompts


@pytest.fixture
def installed_facts(tmp_path, monkeypatch):
    """A small stand-in for `data/facts/`."""
    directory = tmp_path / "facts"
    directory.mkdir()
    (directory / "technologies.json").write_text(json.dumps(["Bronze Working", "Writing"]))
    (directory / "civics.json").write_text(
        json.dumps(["Games and Recreation", "The Enlightenment", "Political Philosophy"])
    )
    (directory / "dedications.json").write_text(
        json.dumps(["Exodus of the Evangelists", "Monumentality", "Pen, Brush, and Voice"])
    )
    (directory / "eras.json").write_text(json.dumps(["Classical Era", "Medieval Era"]))
    (directory / "units.json").write_text(json.dumps(["Great Scientist"]))
    (directory / "governments.json").write_text(json.dumps(["Monarchy"]))

    monkeypatch.setattr(facts, "facts_dir", lambda: directory)
    facts.reload()
    yield directory
    facts.reload()


@pytest.fixture
def no_facts(tmp_path, monkeypatch):
    monkeypatch.setattr(facts, "facts_dir", lambda: tmp_path / "does-not-exist")
    facts.reload()
    yield
    facts.reload()


# ------------------------------------------------------------------ degradation


def test_everything_is_a_no_op_without_installed_facts(no_facts):
    assert facts.available() is False
    assert facts.prompt_block() == ""
    # Crucially: nothing is flagged, rather than everything.
    assert facts.unverified_names("## Tech\n**Exodus of the Evenkind**") == []


def test_the_system_prompt_is_untouched_without_facts(no_facts):
    assert prompts.build_system_prompt("") == prompts.BUILD_SYSTEM_PROMPT


def test_the_facts_block_is_appended_never_substituted(installed_facts):
    combined = prompts.build_system_prompt(facts.prompt_block())
    # The brief's wording survives verbatim.
    assert combined.startswith(prompts.BUILD_SYSTEM_PROMPT)
    assert "Exodus of the Evangelists" in combined


# -------------------------------------------------------------------- catching


def test_a_fabricated_name_is_flagged(installed_facts):
    plan = "## Golden Age Dedications\n- **Exodus of the Evenkind** for faith\n"
    assert facts.unverified_names(plan) == ["Exodus of the Evenkind"]


def test_the_real_name_is_not_flagged(installed_facts):
    plan = "## Golden Age Dedications\n- **Exodus of the Evangelists** for faith\n"
    assert facts.unverified_names(plan) == []


@pytest.mark.parametrize(
    "written",
    [
        "Games & Recreation",      # game spells it "and"
        "Enlightenment",           # game has "The Enlightenment"
        "Classical",               # game has "Classical Era"
        "Medieval",
        "Great Scientists",        # game has the singular
        "Pen, Brush and Voice",    # comma placement drifts
        "Monarchy",
    ],
)
def test_spelling_drift_is_not_a_fabrication(installed_facts, written):
    """These all tripped the first version and were pure noise."""
    assert facts.unverified_names(f"**{written}**") == []


def test_prose_and_numbers_are_never_flagged(installed_facts):
    plan = """## Playbook
- **Turn 1:** settle on the coast
- **5-6 cities** before turn 80
- **Marae in every city** — non-negotiable
- **tempo plays** win here
"""
    assert facts.unverified_names(plan) == []


def test_only_the_coach_s_own_emphasis_is_checked(installed_facts):
    """Unbolded prose isn't an assertion about a name, so it isn't flagged."""
    assert facts.unverified_names("Consider the Evenkind dedication here.") == []


def test_each_name_is_reported_once(installed_facts):
    plan = "**Fakeium Maximus** ... later **Fakeium Maximus** again"
    assert facts.unverified_names(plan) == ["Fakeium Maximus"]


def test_arrow_chains_are_checked_term_by_term(installed_facts):
    plan = "**Bronze Working → Fakeium → Writing**"
    assert facts.unverified_names(plan) == ["Fakeium"]


# ------------------------------------------------- loose phrasing, not fabrication


@pytest.fixture
def people_facts(installed_facts):
    """Leaders as the game disambiguates them, plus a civ."""
    (installed_facts / "leaders.json").write_text(
        json.dumps(["Eleanor of Aquitaine (England)", "Kupe", "Mvemba a Nzinga"])
    )
    (installed_facts / "civilizations.json").write_text(json.dumps(["Kongo"]))
    facts.reload()
    return installed_facts


@pytest.mark.parametrize(
    "written",
    [
        "Eleanor of Aquitaine",   # data disambiguates it with "(England)"
        "Kupe of Maori",          # leader-of-civ phrasing
        "Kongo's Mvemba",         # possessive
    ],
)
def test_loose_leader_phrasing_is_not_a_fabrication(people_facts, written):
    """All three were flagged on a real plan and are just how people write names."""
    assert facts.unverified_names(f"## Tech Path\n**{written}**") == []


def test_the_civ_and_leader_section_is_not_checked(installed_facts):
    """That section is prose about a recommendation, not a list of game entities."""
    plan = """## Civ & Leader
**Some Made Up Civ** is the pick here.

## Tech Path
- **Bronze Working** first
"""
    assert facts.unverified_names(plan) == []


def test_a_fabrication_after_that_section_is_still_caught(installed_facts):
    plan = """## Civ & Leader
**Korea** is the pick.

## Golden Age Dedications
- **Exodus of the Evenkind**
"""
    assert facts.unverified_names(plan) == ["Exodus of the Evenkind"]


# ------------------------------------------------------------- comma-separated runs


def test_a_name_containing_commas_is_not_split(installed_facts):
    assert facts.unverified_names("## Tech\n**Pen, Brush, and Voice**") == []


def test_a_comma_list_of_real_names_is_clean(installed_facts):
    plan = "## Tech Path\n**Bronze Working, Writing**\n"
    assert facts.unverified_names(plan) == []


def test_a_fabrication_inside_a_comma_list_is_caught(installed_facts):
    plan = "## Tech Path\n**Bronze Working, Fakeium, Writing**\n"
    assert facts.unverified_names(plan) == ["Fakeium"]


# ------------------------------------------------------------------ city-states


@pytest.fixture
def city_state_facts(installed_facts):
    (installed_facts / "city_states.json").write_text(
        json.dumps(
            [
                {"name": "Geneva", "category": "Scientific",
                 "bonus": "Your cities earn +15% Science whenever you are not at war."},
                {"name": "Kumasi", "category": "Cultural",
                 "bonus": "Trade Routes to any city-state provide +2 Culture."},
            ]
        )
    )
    facts.reload()
    return installed_facts


def test_city_state_bonuses_reach_the_prompt(city_state_facts):
    """A name alone is useless — "Geneva" only helps with what Geneva does."""
    block = facts.prompt_block()
    assert "Geneva" in block
    assert "+15% Science" in block
    assert "Scientific:" in block


def test_named_city_states_are_not_flagged(city_state_facts):
    plan = "## City-States & Envoys\n- **Geneva** (Scientific) for the science\n"
    assert facts.unverified_names(plan) == []


def test_city_state_categories_are_vocabulary_not_names(city_state_facts):
    """"Ignore Militaristic city-states entirely" flagged on a real plan."""
    plan = "## City-States & Envoys\n- Ignore **Militaristic** city-states entirely\n"
    assert facts.unverified_names(plan) == []
    assert facts.unverified_names("**Cultural city-states**") == []


def test_an_invented_city_state_is_still_caught(city_state_facts):
    plan = "## City-States & Envoys\n- **Genevia** (Scientific) is the one to take\n"
    assert facts.unverified_names(plan) == ["Genevia"]


def test_city_states_are_absent_without_the_file(no_facts):
    assert facts.city_states() == ()
    assert facts.prompt_block() == ""


def test_summary_counts_city_states(city_state_facts):
    """_load() strips the dict entries, so the count has to come from city_states()."""
    assert facts.summary()["city_states"] == 2
    assert facts.summary()["technologies"] == 2


def test_summary_omits_city_states_when_absent(installed_facts):
    assert "city_states" not in facts.summary()
