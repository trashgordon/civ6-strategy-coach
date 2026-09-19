"""The tech and civic trees: fed to the prompt, and used to check the plan's paths."""

import json

import pytest

from backend import facts, tree
from evals import scoring


def _tech(era, cost, *needs):
    return {"era": era, "cost": cost, "needs": list(needs)}


def _unlock(name, kind, by, tree_="technology", civ=""):
    return {"name": name, "kind": kind, "by": by, "tree": tree_, "civ": civ}


STORM = {
    "technologies": {
        "Pottery": _tech("Ancient", 25),
        "Mining": _tech("Ancient", 25),
        "Masonry": _tech("Ancient", 50, "Mining"),
        "Writing": _tech("Ancient", 50, "Pottery"),
        "Currency": _tech("Ancient", 80, "Writing"),
        "Bronze Working": _tech("Ancient", 50, "Mining"),
        "Iron Working": _tech("Classical", 120, "Bronze Working"),
        "Construction": _tech("Classical", 200, "Masonry"),
        "Economics": _tech("Medieval", 400, "Currency"),
    },
    "civics": {
        "Code of Laws": _tech("Ancient", 20),
        "Early Empire": _tech("Ancient", 70, "Code of Laws"),
        "Political Philosophy": _tech("Classical", 110, "Early Empire"),
        "Games and Recreation": _tech("Classical", 110, "Code of Laws"),
        "Drama and Poetry": _tech("Classical", 110, "Code of Laws"),
        "Civil Service": _tech("Medieval", 300, "Political Philosophy"),
    },
    "unlocks": [
        _unlock("Campus", "district", "Writing"),
        _unlock("Commercial Hub", "district", "Currency"),
        _unlock("Ancient Walls", "building", "Masonry"),
        _unlock("Legion", "unit", "Iron Working", civ="Rome"),
        _unlock("Swordsman", "unit", "Iron Working"),
        _unlock("Colosseum", "wonder", "Games and Recreation", "civic"),
        _unlock("Classical Republic", "government", "Political Philosophy", "civic"),
        _unlock("Oligarchy", "government", "Political Philosophy", "civic"),
        _unlock("Discipline", "policy card", "Code of Laws", "civic"),
    ],
    "wonders": {
        "Colosseum": {"effect": "+2 Culture. Must be built on flat land.", "cost": 400,
                      "by": "Games and Recreation"},
    },
}
# Vanilla differs, so the ruleset has to be honoured rather than one tree assumed.
VANILLA = {**STORM, "technologies": {**STORM["technologies"], "Currency": _tech("Ancient", 80, "Pottery")}}


@pytest.fixture
def installed_tree(tmp_path, monkeypatch):
    directory = tmp_path / "facts"
    directory.mkdir()
    (directory / "technologies.json").write_text(json.dumps(sorted(STORM["technologies"])))
    (directory / "civics.json").write_text(json.dumps(sorted(STORM["civics"])))
    (directory / "tree.json").write_text(json.dumps({"Gathering Storm": STORM, "Vanilla": VANILLA}))
    monkeypatch.setattr(facts, "facts_dir", lambda: directory)
    facts.reload()
    yield directory
    facts.reload()


@pytest.fixture
def no_facts(tmp_path, monkeypatch):
    monkeypatch.setattr(facts, "facts_dir", lambda: tmp_path / "nothing-here")
    facts.reload()
    yield
    facts.reload()


def plan(tech="", civic=""):
    return f"## Civ & Leader\n**Rome**\n\n## Tech Path\n{tech}\n\n## Civic Path\n{civic}\n\n## Governors\n- x\n"


def issues(tech="", civic="", ruleset="Gathering Storm"):
    return tree.path_issues(plan(tech, civic), ruleset)


# ----------------------------------------------------------------------- degradation


def test_everything_is_a_no_op_without_the_tree(no_facts):
    assert tree.prompt_section("Gathering Storm") == ""
    assert issues("- **Currency → Writing**") == []


def test_the_eval_check_skips_rather_than_fails_without_the_tree(no_facts):
    assert scoring.score_plan(plan("- **Currency → Writing**"))["checks"]["paths_follow_the_tree"] == scoring.SKIP


# ---------------------------------------------------------------------------- order


def test_a_path_out_of_order_is_flagged(installed_tree):
    assert issues("- **Pottery → Currency → Writing**") == [
        "Currency comes before Writing, but Currency needs Writing first."
    ]


def test_order_is_judged_through_indirect_prerequisites(installed_tree):
    assert issues("- **Currency → Pottery**") == [
        "Currency comes before Pottery, but Currency needs Pottery first."
    ]


def test_a_path_in_order_is_clean(installed_tree):
    assert issues("- **Pottery → Writing → Currency** (early Campus)") == []


def test_names_listed_together_are_not_ordered_against_each_other(installed_tree):
    assert issues("- **Mining → Masonry/Bronze Working → Iron Working**") == []


def test_the_ruleset_decides_the_tree(installed_tree):
    path = "- **Currency → Writing**"
    assert issues(path, ruleset="Gathering Storm")
    assert issues(path, ruleset="Vanilla") == []          # Currency needs only Pottery there


# ------------------------------------------------------------------------ wrong tree


def test_a_civic_in_the_tech_path_is_flagged(installed_tree):
    assert issues("- **Writing → Civil Service**") == [
        "Civil Service is a civic, but it's listed in the tech path."
    ]


def test_a_tech_in_the_civic_path_is_flagged(installed_tree):
    assert issues(civic="- **Code of Laws → Currency**") == [
        "Currency is a tech, but it's listed in the civic path."
    ]


def test_an_ampersand_name_is_still_recognised(installed_tree):
    assert issues("- **Writing → Drama & Poetry**") == [
        "Drama and Poetry is a civic, but it's listed in the tech path."
    ]


# ---------------------------------------------------------------------- unlock claims


def test_crediting_the_wrong_unlock_is_flagged(installed_tree):
    assert issues(civic="- **Civil Service** for Classical Republic") == [
        "Classical Republic is unlocked by Political Philosophy (civic), not Civil Service."
    ]


def test_crediting_the_right_unlock_is_clean(installed_tree):
    assert issues(civic="- **Political Philosophy** for Classical Republic ASAP") == []


def test_every_name_in_a_listed_claim_is_checked(installed_tree):
    found = issues("- **Masonry → Construction** for Ancient Walls/Colosseum")
    assert found == ["Colosseum is unlocked by Games and Recreation (civic), not Construction or Masonry."]


def test_plural_unit_names_are_recognised(installed_tree):
    assert issues("- **Bronze Working** early for Legions") == [
        "Legion is unlocked by Iron Working (tech), not Bronze Working."
    ]


@pytest.mark.parametrize("line", [
    "- **Mining** early for farm-adjacent Campus prep",          # a bonus, not the unlock
    "- **Mining** skip unless needed for Campus buffs",
    "- **Mining** for a long, patient buildup and eventually Campus",  # too far from "for"
    "- **Mining** first; grab Campus when Writing lands",         # no claim at all
])
def test_loose_phrasing_is_not_an_unlock_claim(installed_tree, line):
    assert issues(line) == []


def test_a_district_you_already_have_can_be_what_a_later_tech_is_for(installed_tree):
    # Currency comes before Economics, and hubs keep paying off.
    assert issues("- **Economics** for Commercial Hub snowball") == []


def test_a_government_is_a_one_off_unlock_even_when_you_already_have_it(installed_tree):
    assert issues(civic="- **Civil Service** for Oligarchy") == [
        "Oligarchy is unlocked by Political Philosophy (civic), not Civil Service."
    ]


def test_lowercase_words_are_not_game_names(installed_tree):
    assert issues("- **Pottery → Writing**, then keep mining under construction") == []


def test_only_the_path_sections_are_checked(installed_tree):
    text = plan() + "\n## The Playbook\n- **Currency → Writing** for Colosseum\n"
    assert tree.path_issues(text, "Gathering Storm") == []


# --------------------------------------------------------------------------- prompt


def test_the_tree_reaches_the_prompt_for_the_briefing_s_ruleset(installed_tree):
    block = facts.prompt_block(ruleset="Gathering Storm")
    assert "- Writing (Ancient) ← Pottery → Campus" in block
    assert "Legion [Rome only]" in block
    assert "- Currency (Ancient) ← Writing" in block
    assert "- Currency (Ancient) ← Pottery" in facts.prompt_block(ruleset="Vanilla")


def test_the_tree_replaces_the_plain_tech_and_civic_lists(installed_tree):
    block = facts.prompt_block(ruleset="Gathering Storm")
    assert "Technologies:\n- Mining (Ancient)\n- Pottery" in block   # the tree's, cheapest first
    assert "Technologies:\n- Bronze Working" not in block   # not the alphabetical one


def test_an_unknown_ruleset_falls_back_to_gathering_storm(installed_tree):
    assert tree.prompt_section("Civ VII") == tree.prompt_section("Gathering Storm")


def test_generation_sends_the_briefing_s_ruleset(installed_tree):
    from backend import generation
    assert "← Pottery" in generation.system_prompt("Vanilla").split("- Currency (Ancient)")[1][:20]


def test_the_eval_check_fails_a_plan_that_breaks_the_tree(installed_tree):
    score = scoring.score_plan(plan("- **Currency → Writing**"), "Gathering Storm")
    assert score["checks"]["paths_follow_the_tree"] == scoring.FAIL
    assert score["tree_issues"]


def test_a_claim_belongs_to_the_chain_step_it_is_written_in(installed_tree):
    # "into later civics" names no civic, so nothing earlier in the chain is credited.
    assert issues(civic="- **Code of Laws → Early Empire → into later civics for Oligarchy**") == []
    # ...but a claim made in a named step is still checked.
    assert issues(civic="- **Code of Laws → Early Empire** for Oligarchy") == [
        "Oligarchy is unlocked by Political Philosophy (civic), not Code of Laws or Early Empire."
    ]


def test_holding_out_for_an_unlock_is_not_a_claim_about_it(installed_tree):
    assert issues(civic="- **Civil Service** (or hold for Oligarchy)") == []


def test_wonders_reach_the_prompt_with_effect_placement_and_unlock(installed_tree):
    block = facts.prompt_block(ruleset="Gathering Storm")
    assert "- Colosseum (Games and Recreation, 400 production): +2 Culture. Must be built on flat land." in block


# --------------------------------------------------------------------------- wonders


def wonders_plan(body):
    return plan() + f"\n## Wonders\n{body}\n"


def test_a_wonder_s_bracketed_unlock_must_be_the_real_one(installed_tree):
    assert tree.path_issues(wonders_plan("- **Colosseum** (Construction): amenities"), "Gathering Storm") == [
        "Colosseum is unlocked by Games and Recreation (civic), not Construction."
    ]
    assert tree.path_issues(wonders_plan("- **Colosseum** (Games and Recreation) first"), "Gathering Storm") == []


def test_a_bracket_without_a_tech_or_civic_is_not_a_claim(installed_tree):
    assert tree.path_issues(wonders_plan("- **Colosseum** (capital, flat land)"), "Gathering Storm") == []


def test_for_claims_are_checked_in_the_wonders_section_too(installed_tree):
    assert tree.path_issues(wonders_plan("- Beeline **Construction** for Colosseum"), "Gathering Storm") == [
        "Colosseum is unlocked by Games and Recreation (civic), not Construction."
    ]


def test_order_and_tree_checks_stay_in_the_path_sections(installed_tree):
    # A wonder section may mention techs and civics in any order it likes.
    assert tree.path_issues(wonders_plan("- After **Currency → Writing**, start Colosseum"), "Gathering Storm") == []


@pytest.mark.parametrize("body, verdict", [
    ("- **Colosseum** (Games and Recreation) in the capital. Backup: more Arenas.", "pass"),
    ("- **Colosseum** if it gets sniped, build Arenas instead", "pass"),
    ("- **Colosseum** in the capital, start by T60", "fail"),          # no way out
    ("Domination build: skip wonders, every hammer goes to units.", "pass"),
    ("Nothing to say here.", "fail"),
])
def test_the_eval_wants_priorities_with_backups_or_a_clear_no(installed_tree, body, verdict):
    assert scoring.score_plan(wonders_plan(body), "Gathering Storm")["checks"]["wonders_have_backups"] == verdict


def test_a_claim_about_a_whole_path_names_the_missing_unlock_not_every_step(installed_tree):
    assert issues("- **Pottery → Writing → Currency**, then onward for Colosseum") == []  # "onward" step
    assert issues("- **Pottery → Writing → Currency → Economics** for Colosseum") == [
        "Colosseum is unlocked by Games and Recreation (civic), which isn't in this path."
    ]
