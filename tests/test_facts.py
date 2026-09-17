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


# ------------------------------------------- slashes, imperatives, and list vouching


def test_a_slash_inside_prose_does_not_yield_a_bare_word(city_state_facts):
    """"**Tech/civic stagnation from ignoring economy**" flagged a bare "Tech"."""
    plan = "## What Goes Wrong\n- **Tech/civic stagnation from ignoring economy**: ...\n"
    assert facts.unverified_names(plan) == []


def test_a_bolded_imperative_is_an_instruction_not_a_name(city_state_facts):
    plan = "## City-States & Envoys\n- **Ignore** Militaristic city-states entirely\n"
    assert facts.unverified_names(plan) == []


def test_slash_separated_names_are_checked_individually(city_state_facts):
    (city_state_facts / "city_states.json").write_text(
        json.dumps(
            [
                {"name": "Amsterdam", "category": "Trade", "bonus": "Trade bonus."},
                {"name": "Venice", "category": "Trade", "bonus": "Trade bonus."},
            ]
        )
    )
    facts.reload()
    assert facts.unverified_names("**Amsterdam/Venice**") == []
    # A real name must not vouch for a fabricated one beside it.
    assert facts.unverified_names("**Amsterdam/Genevia**") == ["Genevia"]


def test_loose_phrasing_still_forgiven_when_there_is_no_list(people_facts):
    """Containment is narrowed to non-list terms, but must still work for these."""
    assert facts.unverified_names("**Kongo's Mvemba**") == []
    assert facts.unverified_names("**Kupe / Māori**") == []


def test_a_possessive_reference_to_a_real_name_is_not_a_fabrication(installed_facts):
    """"Political Philosophy's Monarchic Legacy" flagged on a real plan."""
    plan = "## Government\n- **Political Philosophy's Monarchic Legacy** when available\n"
    assert facts.unverified_names(plan) == []


def test_a_possessive_around_a_fabrication_is_still_caught(installed_facts):
    assert facts.unverified_names("**Fakeium's Fakery**") == ["Fakeium's Fakery"]


def test_accented_names_fold_to_their_plain_spelling(installed_facts):
    """The civ list says "Maori"; plans write "Māori". Both must be the same name."""
    assert facts.unverified_names("**Māori**") == []
    assert facts.unverified_names("**Maori**") == []


def test_folding_survives_a_slash_split(people_facts):
    """Splitting on "/" checks each half, so both must fold — "Kupe" and "Māori"."""
    assert facts.unverified_names("**Kupe / Māori**") == []


# ---------------------------------------------------------------- effect grounding


@pytest.fixture
def effect_facts(installed_facts):
    (installed_facts / "policy_cards.json").write_text(
        json.dumps(["Corvée", "Colonization", "Serfdom"])
    )
    (installed_facts / "abilities.json").write_text(
        json.dumps(["Trajan's Column"])
    )
    (installed_facts / "effects.json").write_text(
        json.dumps(
            {
                "Corvée": "+15% Production toward Ancient and Classical wonders.",
                "Colonization": "+50% Production toward Settlers.",
                "Trajan's Column": "All cities start with an additional City Center building.",
            }
        )
    )
    facts.reload()
    return installed_facts


def test_effects_reach_the_prompt_beside_their_names(effect_facts):
    """The bug this exists for: the coach kept calling Corvée a settler card."""
    block = facts.prompt_block()
    assert "- Corvée: +15% Production toward Ancient and Classical wonders." in block
    assert "- Colonization: +50% Production toward Settlers." in block


def test_a_name_with_no_recorded_effect_is_still_listed(effect_facts):
    """Serfdom has no effect in this fixture — the name must not disappear."""
    block = facts.prompt_block()
    assert "- Serfdom" in block
    assert "- Serfdom:" not in block


def test_civ_abilities_are_injected_with_their_effects(effect_facts):
    block = facts.prompt_block()
    assert "Civ and leader abilities:" in block
    assert "- Trajan's Column: All cities start with an additional" in block


def test_the_prompt_tells_the_model_not_to_recall_effects(effect_facts):
    block = facts.prompt_block()
    assert "as it is written here" in block


def test_effects_are_optional(no_facts):
    assert facts.effects() == {}
    assert facts.prompt_block() == ""


def test_effects_do_not_leak_into_name_validation(effect_facts):
    """effects.json is a mapping; the name loader must skip it, not choke on it."""
    assert "effects" not in facts.summary()
    assert facts.unverified_names("**Corvée**") == []
