"""The eval harness's scorer. If this is wrong, every eval number is wrong."""

import pytest

from backend import facts
from evals import run, scoring

HEADERS = scoring.expected_headers()


def plan(sections: dict[str, str] | None = None, words_padding: int = 0) -> str:
    """A plan with every expected header, bodies overridable per section."""
    bodies = {
        "Timing Benchmarks": "- T30: 3 cities\n- T60: Campus everywhere\n- T90: Universities",
        "What Goes Wrong": "- Early war\n- Amenities crunch",
        "Dedications": "- Golden age: Free Inquiry\n- Normal or dark age: farm era score",
        "The Playbook": "\n".join(f"- step {i}" for i in range(1, 7)),
    }
    bodies.update(sections or {})
    parts = [f"## {h}\n{bodies.get(h, 'Some advice.')}" for h in HEADERS]
    return "\n\n".join(parts) + (" word" * words_padding)


@pytest.fixture(autouse=True)
def without_facts(tmp_path, monkeypatch):
    """Most checks must work with no game data installed."""
    monkeypatch.setattr(facts, "facts_dir", lambda: tmp_path / "none")
    facts.reload()
    yield
    facts.reload()


def test_expectations_are_read_from_the_live_prompt():
    """Editing the prompt must not leave the eval checking stale rules."""
    assert len(HEADERS) == 13
    assert HEADERS[4] == "Wonders"
    assert HEADERS[0] == "Civ & Leader" and HEADERS[-1] == "The Playbook"
    assert scoring.word_cap() == 1200


def test_a_well_formed_plan_passes_everything_it_can_judge():
    checks = scoring.score_plan(plan())["checks"]
    judged = {k: v for k, v in checks.items() if v != scoring.SKIP}
    assert set(judged.values()) == {scoring.PASS}, judged


def test_facts_dependent_checks_skip_rather_than_fail_without_facts():
    checks = scoring.score_plan(plan())["checks"]
    for name in ("city_states_named_2plus", "governor_promotions_named",
                 "no_unverified_names"):
        assert checks[name] == scoring.SKIP


def test_a_missing_or_renamed_header_fails():
    renamed = plan().replace("## Dedications", "## Golden Age Dedications")
    assert scoring.score_plan(renamed)["checks"]["headers_exact"] == scoring.FAIL


def test_the_word_cap_is_enforced():
    assert scoring.score_plan(plan(words_padding=1200))["checks"]["within_word_cap"] == scoring.FAIL


@pytest.mark.parametrize("bullets, verdict", [(4, "fail"), (5, "pass"), (8, "pass"), (9, "fail")])
def test_playbook_must_have_five_to_eight_steps(bullets, verdict):
    body = "\n".join(f"- step {i}" for i in range(bullets))
    assert scoring.score_plan(plan({"The Playbook": body}))["checks"]["playbook_5_to_8"] == verdict


def test_benchmark_turns_are_parsed_in_every_format_the_coach_uses():
    body = "- **T30–35**: three cities\n- turn ~110: Classical Republic\n- Turn 220: Education"
    assert scoring.benchmark_turns(plan({"Timing Benchmarks": body})) == [30, 110, 220]


def test_dedications_must_cover_a_non_golden_age():
    golden_only = plan({"Dedications": "- Golden Age: Free Inquiry"})
    assert scoring.score_plan(golden_only)["checks"]["dedications_cover_ages"] == scoring.FAIL


@pytest.mark.parametrize(
    "text, tripwire",
    [
        ("Slot Corvée for builder speed while sprawling", "corvee-misattributed"),
        ("Corvée for wide infrastructure/settlers", "corvee-misattributed"),
        ("Sign Research Agreements with your neighbours", "research-agreements"),
        ("Beeline Physics", "physics-tech"),
        ("Rome's uniques (Legion, Balista)", "balista"),
        ("Exodus of the Evenkind", "evenkind"),
        ("Don't bother with Victor (Sanguine Pact)", "victor-secret-society"),
    ],
)
def test_known_wrong_claims_trip(text, tripwire):
    """Every claim the coach has been caught making. Prose counts — unlike the
    name validator, these don't need the coach to have bolded anything."""
    hits = scoring.score_plan(plan({"Government & Policy Cards": text}))["known_wrong"]
    assert tripwire in {h["id"] for h in hits}


def test_correct_uses_do_not_trip():
    fine = "Corvée for the Pyramids and Colossus. Form a Research Alliance. Victor in the border city."
    assert scoring.score_plan(plan({"Government & Policy Cards": fine}))["known_wrong"] == []


def test_speed_scaling_compares_marathon_against_standard():
    def result(brief, turns):
        return {"brief": brief, "score": {"benchmark_turns": turns}}

    scaled = [result("std", [30, 60, 90]), result("mar", [110, 180, 280])]
    flat = [result("std", [30, 60, 90]), result("mar", [35, 70, 95])]
    assert scoring.speed_scaling(scaled, "std", "mar") == scoring.PASS
    assert scoring.speed_scaling(flat, "std", "mar") == scoring.FAIL
    assert scoring.speed_scaling([], "std", "mar") == scoring.SKIP


def test_briefs_file_is_well_formed():
    base, briefs = run.load_briefs()
    ids = [b["id"] for b in briefs]
    assert len(ids) == len(set(ids)), "brief ids must be unique"
    assert all(b.get("why") for b in briefs), "every brief says what it's for"
    assert "science-tall-korea" in ids and "science-marathon-korea" in ids


def test_summary_counts_pass_rates_and_tripwires():
    good = {"brief": "a", "score": scoring.score_plan(plan()), "cost_usd": 0.03}
    bad_plan = plan({"Government & Policy Cards": "Corvée for settlers"})
    bad = {"brief": "b", "score": scoring.score_plan(bad_plan), "cost_usd": 0.03}
    errored = {"brief": "c", "error": "boom"}

    summary = run.summarise([good, bad, errored])
    assert summary["plans"] == 2
    assert summary["errors"] == 1
    assert summary["check_pass_rates"]["no_known_wrong_claims"] == 0.5
    assert summary["known_wrong_tripped"] == {"corvee-misattributed": 1}
    assert summary["cost_usd"] == 0.06
