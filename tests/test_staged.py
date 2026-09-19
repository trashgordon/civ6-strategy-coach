"""The staged pipeline: decide as JSON, check exactly, repair, then write."""

import asyncio
import json

import pytest

from backend import facts, generation, llm, staged
from tests.test_tree import STORM


@pytest.fixture
def game_data(tmp_path, monkeypatch):
    d = tmp_path / "facts"
    d.mkdir()
    (d / "tree.json").write_text(json.dumps({"Gathering Storm": STORM}))
    (d / "governments.json").write_text(json.dumps(["Classical Republic", "Oligarchy"]))
    (d / "policy_cards.json").write_text(json.dumps(["Discipline", "Agoge"]))
    (d / "city_states.json").write_text(json.dumps([
        {"name": "Geneva", "category": "Scientific", "bonus": "+15% Science"}]))
    (d / "governor_kits.json").write_text(json.dumps([
        {"governor": "Pingala", "promotions": [{"name": "Researcher"}, {"name": "Grants"}]},
        {"governor": "Magnus", "promotions": [{"name": "Provision"}]}]))
    monkeypatch.setattr(facts, "facts_dir", lambda: d)
    facts.reload()
    yield
    facts.reload()


GOOD = {
    "civ": "Rome", "leader": "Trajan", "victory": "Domination", "why": "x",
    "tech_path": ["Mining", "Bronze Working", "Iron Working"],
    "civic_path": ["Code of Laws", "Early Empire", "Political Philosophy"],
    "governments": ["Classical Republic"], "policy_cards": ["Discipline"],
    "wonders": [{"name": "Colosseum", "city": "capital", "start_turn": 60, "backup": "Arenas"}],
    "wonder_to_skip": "Colosseum",
    "city_states": [{"name": "Geneva", "envoys": 3}],
    "governors": [{"name": "Pingala", "city": "capital", "promotions": ["Researcher"]}],
    "benchmarks": [{"turn": 30, "milestone": "a"}, {"turn": 60, "milestone": "b"}],
}


def test_clean_decisions_pass(game_data):
    assert staged.check_decisions(GOOD, "Gathering Storm") == []


@pytest.mark.parametrize("change, expected", [
    ({"tech_path": ["Iron Working", "Bronze Working"]},
     "tech_path: Iron Working is listed before Bronze Working, but Iron Working needs Bronze Working first."),
    ({"tech_path": ["Mining", "Civil Service"]},
     "tech_path: Civil Service is a civic, not a technology — move it to the other path."),
    ({"civic_path": ["Code of Laws", "Physics"]}, "civic_path: 'Physics' isn't a civic in Gathering Storm."),
    ({"governors": [{"name": "Pingala", "promotions": ["Provision"]}]},
     "governors: 'Provision' isn't one of Pingala's promotions (theirs: Grants, Researcher)."),
    ({"city_states": [{"name": "Genevia"}]}, "city_states: 'Genevia' isn't a city-state in the game."),
    ({"wonders": [{"name": "Colossus of Nowhere"}]}, "wonders: 'Colossus of Nowhere' isn't a wonder in Gathering Storm."),
    ({"benchmarks": [{"turn": 60}, {"turn": 30}]}, "benchmarks: turns must rise in order, got [60, 30]."),
    ({"civ": "Atlantis"}, "civ: 'Atlantis' isn't a civilization I recognise."),
])
def test_each_contradiction_is_named_exactly(game_data, change, expected):
    assert staged.check_decisions({**GOOD, **change}, "Gathering Storm") == [expected]


def test_json_is_found_inside_fences_or_chatter():
    assert staged.parse_decisions('Here:\n```json\n{"civ": "Rome"}\n```') == {"civ": "Rome"}
    assert staged.parse_decisions("no json here") is None


def _replies(monkeypatch, texts):
    calls = []

    async def fake(system_prompt, user_prompt, max_tokens, reasoning_effort=None):
        calls.append({"user": user_prompt, "effort": reasoning_effort})
        return llm.Completion(text=texts[len(calls) - 1], model="m", prompt_tokens=10,
                              completion_tokens=5, cost_usd=0.01)

    monkeypatch.setattr(llm, "complete", fake)
    return calls


def test_errors_go_back_to_the_strategist_and_the_writer_gets_the_fix(game_data, monkeypatch):
    bad = {**GOOD, "tech_path": ["Iron Working", "Bronze Working"]}
    calls = _replies(monkeypatch, [json.dumps(bad), json.dumps(GOOD), "## Civ & Leader\n**Rome**"])
    result = asyncio.run(staged.draft_plan(config={"ruleset": "Gathering Storm"},
                                           user_prompt="USER", system_prompt="SYS"))
    assert len(calls) == 3
    assert "Iron Working needs Bronze Working first" in calls[1]["user"]      # the repair
    assert '"Bronze Working"' in calls[2]["user"] and calls[2]["effort"] == "low"  # writer
    assert calls[0]["effort"] == "medium"
    assert result.text == "## Civ & Leader\n**Rome**"
    assert result.detail["repairs"] == 1 and result.detail["errors_left"] == []
    assert result.cost_usd == pytest.approx(0.03)            # every call is paid for


def test_repairs_stop_after_two_rounds_and_the_plan_is_still_written(game_data, monkeypatch):
    bad = json.dumps({**GOOD, "civ": "Atlantis"})
    calls = _replies(monkeypatch, [bad, bad, bad, "## Civ & Leader\n**Atlantis**"])
    result = asyncio.run(staged.draft_plan(config={}, user_prompt="U", system_prompt="S"))
    assert len(calls) == 4
    assert result.detail["errors_left"] == ["civ: 'Atlantis' isn't a civilization I recognise."]


def test_the_pipeline_defaults_to_staged(monkeypatch):
    monkeypatch.delenv("PIPELINE", raising=False)
    assert generation.pipeline() == "staged"
    monkeypatch.setenv("PIPELINE", "single")
    assert generation.pipeline() == "single"
    monkeypatch.setenv("PIPELINE", "nonsense")
    assert generation.pipeline() == "staged"


def test_a_staged_build_keeps_its_decisions_and_every_call_s_cost(game_data, monkeypatch, client, sample_config):
    monkeypatch.setenv("PIPELINE", "staged")
    _replies(monkeypatch, [json.dumps(GOOD), "## Civ & Leader\n**Rome**"])
    build = client.post("/api/generate", json={"config": sample_config}).json()
    assert build["decisions"]["civ"] == "Rome"
    assert build["usage"]["calls"] == 2
    assert build["usage"]["cost_usd"] == pytest.approx(0.02)
    # Still there when it's read back from the archive.
    assert client.get(f"/api/builds/{build['id']}").json()["decisions"] == GOOD


def test_a_real_name_with_an_aside_is_still_that_name(game_data):
    decisions = {**GOOD, "wonder_to_skip": "Colosseum (amenities this build doesn't need)",
                 "tech_path": ["Mining", "Bronze Working (for Encampments)", "Iron Working"]}
    assert staged.check_decisions(decisions, "Gathering Storm") == []


def test_an_aside_does_not_rescue_a_made_up_name(game_data):
    decisions = {**GOOD, "wonder_to_skip": "Colossus of Nowhere (tempting)"}
    assert staged.check_decisions(decisions, "Gathering Storm") == [
        "wonder_to_skip: 'Colossus of Nowhere (tempting)' isn't a wonder in Gathering Storm."
    ]


def test_a_name_that_merely_starts_like_a_real_one_is_not_it(game_data):
    # "Mining" must not vouch for "Miningtown".
    assert staged.check_decisions({**GOOD, "tech_path": ["Miningtown"]}, "Gathering Storm") == [
        "tech_path: 'Miningtown' isn't a technology in Gathering Storm."
    ]


def test_the_writer_is_told_what_unlocks_each_decided_item(game_data, monkeypatch):
    calls = _replies(monkeypatch, [json.dumps(GOOD), "## Civ & Leader\n**Rome**"])
    asyncio.run(staged.draft_plan(config={"ruleset": "Gathering Storm"}, user_prompt="U", system_prompt="S"))
    sent = json.loads(calls[-1]["user"].split("Decided plan:\n", 1)[1])
    assert sent["unlocked_by"] == {
        "Colosseum": "Games and Recreation (civic)",          # a decided wonder
        "Classical Republic": "Political Philosophy (civic)",  # a decided government
        "Discipline": "Code of Laws (civic)",                  # a decided card
        "Legion": "Iron Working (tech)",                       # Rome's unique
    }


def test_the_saved_decisions_stay_as_decided(game_data, monkeypatch):
    _replies(monkeypatch, [json.dumps(GOOD), "## Civ & Leader\n**Rome**"])
    result = asyncio.run(staged.draft_plan(config={"ruleset": "Gathering Storm"}, user_prompt="U", system_prompt="S"))
    assert "unlocked_by" not in result.detail["decisions"]
