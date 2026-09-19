"""End-to-end coverage of the MVP loop: generate -> auto-save -> archive -> compare."""

from tests.conftest import SAMPLE_PLAN


def _generate(client, sample_config, **overrides):
    payload = {
        "config": sample_config,
        "civ": "Korea",
        "city_philosophy": "Tall",
        "primary_focus": "Science",
        "posture": "Introverted / peaceful",
        "playstyle_text": "Few cities, big science, leave me alone.",
    }
    payload.update(overrides)
    response = client.post("/api/generate", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_meta_reports_no_auth_by_default(client):
    body = client.get("/api/meta").json()
    assert body["auth_required"] is False
    assert body["authenticated"] is True
    assert body["model"] == "anthropic/claude-sonnet-4-6"


def test_generate_auto_saves_and_returns_the_build(client, sample_config, stub_llm):
    build = _generate(client, sample_config)

    assert build["id"] > 0
    # Saved as written, apart from headers put back to their exact names.
    from backend.generation import tidy_headers
    assert build["generated_plan"] == tidy_headers(SAMPLE_PLAN)
    assert build["civ"] == "Korea"
    assert build["primary_focus"] == "Science"
    # Denormalized for archive filtering.
    assert build["ruleset"] == "Gathering Storm"
    assert build["map_type"] == "Pangaea"
    # Full config round-trips, nested modes included.
    assert build["config"]["modes"]["monopolies"] is True

    # It really is saved, not just returned.
    assert client.get(f"/api/builds/{build['id']}").json()["id"] == build["id"]


def test_generate_sends_config_and_styles_to_the_model(client, sample_config, stub_llm):
    _generate(client, sample_config)

    system, user = stub_llm[0]["system"], stub_llm[0]["user"]
    assert "former competitive Civilization VI player" in system
    assert "the freeform description wins" in system

    assert "- Ruleset: Gathering Storm" in user
    assert "Pangaea, Standard size" in user
    assert "Monopolies and Corporations Mode" in user
    assert "Sukritact's Oceans" in user
    assert "Apocalypse Mode" not in user          # off, so not mentioned
    assert "Civ preference: Korea" in user
    assert "- City philosophy: Tall" in user
    assert "- Primary focus: Science" in user
    assert "Few cities, big science" in user


def test_no_preference_reads_as_no_preference(client, sample_config, stub_llm):
    _generate(
        client,
        sample_config,
        civ="",
        city_philosophy="No preference",
        primary_focus="No preference",
        posture="No preference",
        playstyle_text="",
    )
    user = stub_llm[0]["user"]
    assert "Civ preference: No preference — recommend the best fit." in user
    assert "- City philosophy: No preference — call it for this build" in user
    assert "Not specified — recommend a strong, fun build" in user


def test_title_is_suggested_from_the_build(client, sample_config, stub_llm):
    build = _generate(client, sample_config)
    assert build["title"] == "Korea — Science, Tall, Introverted"


def test_title_falls_back_to_the_plan_when_no_civ_was_picked(
    client, sample_config, stub_llm
):
    build = _generate(client, sample_config, civ="", city_philosophy="", posture="")
    # Read out of the plan's first section.
    assert build["title"] == "Korea — Science"


def test_archive_lists_newest_first_and_omits_plan_bodies(
    client, sample_config, stub_llm
):
    first = _generate(client, sample_config, civ="Korea")
    second = _generate(client, sample_config, civ="Rome")

    body = client.get("/api/builds").json()
    ids = [b["id"] for b in body["builds"]]
    assert ids == [second["id"], first["id"]]
    assert "generated_plan" not in body["builds"][0]
    assert body["filters"]["civs"] == ["Korea", "Rome"]


def test_archive_search_and_filter(client, sample_config, stub_llm):
    _generate(client, sample_config, civ="Korea", playstyle_text="turtle and tech")
    _generate(
        client,
        sample_config,
        civ="Rome",
        primary_focus="Domination",
        playstyle_text="legions everywhere",
    )

    assert len(client.get("/api/builds?q=legions").json()["builds"]) == 1
    assert len(client.get("/api/builds?civ=Korea").json()["builds"]) == 1
    assert len(client.get("/api/builds?primary_focus=Domination").json()["builds"]) == 1
    assert len(client.get("/api/builds?q=nothing-matches-this").json()["builds"]) == 0
    # Search reaches into the plan text too.
    assert len(client.get("/api/builds?q=Seowon").json()["builds"]) == 2


def test_rename_and_delete(client, sample_config, stub_llm):
    build = _generate(client, sample_config)

    renamed = client.patch(f"/api/builds/{build['id']}", json={"title": "Seowon spam"})
    assert renamed.json()["title"] == "Seowon spam"

    assert client.patch(f"/api/builds/{build['id']}", json={"title": "  "}).status_code == 422

    assert client.delete(f"/api/builds/{build['id']}").status_code == 200
    assert client.get(f"/api/builds/{build['id']}").status_code == 404
    assert client.delete(f"/api/builds/{build['id']}").status_code == 404


def test_compare_returns_a_table_and_a_writeup(client, sample_config, stub_llm):
    first = _generate(client, sample_config, civ="Korea")
    second = _generate(
        client, sample_config, civ="Rome", primary_focus="Domination", posture="Aggressive / militaristic"
    )

    response = client.post(
        "/api/compare", json={"build_ids": [first["id"], second["id"]]}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert [row["civ"] for row in body["rows"]] == ["Korea", "Rome"]
    assert body["rows"][1]["primary_focus"] == "Domination"
    # Key terms are lifted out of the plan's tech/civic sections.
    assert "Writing" in body["rows"][0]["key_terms"]
    assert "Political Philosophy" in body["rows"][0]["key_terms"]
    assert "Seowon" in body["writeup"]

    # The compare prompt is the second one, and it carries both plans.
    compare_call = stub_llm[-1]
    assert "compare-and-contrast" in compare_call["system"]
    assert compare_call["user"].count("=== Build") == 2


def test_compare_needs_at_least_two_real_builds(client, sample_config, stub_llm):
    build = _generate(client, sample_config)

    assert client.post("/api/compare", json={"build_ids": [build["id"]]}).status_code == 422
    # Duplicates collapse, so this is really a single build.
    assert client.post(
        "/api/compare", json={"build_ids": [build["id"], build["id"]]}
    ).status_code == 422
    assert client.post(
        "/api/compare", json={"build_ids": [build["id"], 9999]}
    ).status_code == 404


def test_model_failures_surface_as_502(client, sample_config, monkeypatch):
    from backend import llm

    async def boom(*args, **kwargs):
        raise llm.LLMError("no key configured")

    monkeypatch.setattr(llm, "complete", boom)
    response = client.post("/api/generate", json={"config": sample_config})
    assert response.status_code == 502
    assert "no key configured" in response.json()["detail"]


def test_key_terms_skip_what_the_plan_says_to_skip():
    """A bolded tech inside "skip Iron Working" is not a key tech."""
    from backend import summarize

    plan = """## Tech path
- **Writing** first, then **Currency**
- Skip **Iron Working** entirely on Prince — you don't need it
- Don't bother with **Military Tactics**
- **Education** for Universities
"""
    terms = summarize.key_techs_and_wonders(plan)
    assert terms == ["Writing", "Currency", "Education"]


def test_campaign_journal_round_trips(client, sample_config, stub_llm):
    build = _generate(client, sample_config)
    assert build["notes"] == ""

    notes = "Turn 40: forward-settled by Rome. Going Encampment before Campus."
    updated = client.patch(f"/api/builds/{build['id']}", json={"notes": notes})
    assert updated.status_code == 200, updated.text
    assert updated.json()["notes"] == notes
    # Title survives a notes-only edit.
    assert updated.json()["title"] == build["title"]

    assert client.get(f"/api/builds/{build['id']}").json()["notes"] == notes


def test_notes_can_be_cleared_and_renaming_leaves_them_alone(
    client, sample_config, stub_llm
):
    build = _generate(client, sample_config)
    client.patch(f"/api/builds/{build['id']}", json={"notes": "some notes"})

    renamed = client.patch(f"/api/builds/{build['id']}", json={"title": "New name"})
    assert renamed.json()["title"] == "New name"
    assert renamed.json()["notes"] == "some notes"

    cleared = client.patch(f"/api/builds/{build['id']}", json={"notes": ""})
    assert cleared.json()["notes"] == ""


def test_an_empty_patch_is_harmless(client, sample_config, stub_llm):
    build = _generate(client, sample_config)
    response = client.patch(f"/api/builds/{build['id']}", json={})
    assert response.status_code == 200
    assert response.json()["title"] == build["title"]


def test_patching_a_missing_build_is_404(client):
    assert client.patch("/api/builds/9999", json={"notes": "x"}).status_code == 404


def test_logging_an_outcome_round_trips(client, sample_config, stub_llm):
    build = _generate(client, sample_config)
    assert (build["outcome"], build["victory_type"], build["end_turn"]) == ("", "", None)

    logged = client.patch(
        f"/api/builds/{build['id']}",
        json={"outcome": "won", "victory_type": "Science", "end_turn": 247},
    )
    assert logged.status_code == 200, logged.text
    assert logged.json()["outcome"] == "won"
    assert logged.json()["victory_type"] == "Science"
    assert logged.json()["end_turn"] == 247
    # And it survives a reload.
    assert client.get(f"/api/builds/{build['id']}").json()["end_turn"] == 247


def test_outcome_input_is_validated(client, sample_config, stub_llm):
    build = _generate(client, sample_config)
    url = f"/api/builds/{build['id']}"

    assert client.patch(url, json={"outcome": "sort of won"}).status_code == 422
    assert client.patch(url, json={"victory_type": "Vibes"}).status_code == 422
    assert client.patch(url, json={"end_turn": -5}).status_code == 422
    assert client.patch(url, json={"end_turn": 99999}).status_code == 422

    # Case is forgiven, and the canonical spelling comes back.
    assert client.patch(url, json={"outcome": "WON"}).json()["outcome"] == "won"
    assert client.patch(
        url, json={"victory_type": "science"}
    ).json()["victory_type"] == "Science"


def test_an_outcome_can_be_unrecorded_again(client, sample_config, stub_llm):
    build = _generate(client, sample_config)
    url = f"/api/builds/{build['id']}"
    client.patch(url, json={"outcome": "lost", "end_turn": 120})

    cleared = client.patch(url, json={"outcome": "", "end_turn": 0})
    assert cleared.json()["outcome"] == ""
    assert cleared.json()["end_turn"] is None


def test_stats_endpoint_summarises_the_archive(client, sample_config, stub_llm):
    empty = client.get("/api/stats").json()
    assert empty["overall"]["builds"] == 0
    assert empty["overall"]["win_rate"] is None
    assert empty["outcomes"] == ["won", "lost", "abandoned"]
    assert "Science" in empty["victory_types"]

    first = _generate(client, sample_config, civ="Korea")
    second = _generate(client, sample_config, civ="Korea")
    third = _generate(client, sample_config, civ="Rome", primary_focus="Domination")
    client.patch(f"/api/builds/{first['id']}",
                 json={"outcome": "won", "victory_type": "Science", "end_turn": 240})
    client.patch(f"/api/builds/{second['id']}", json={"outcome": "lost"})
    client.patch(f"/api/builds/{third['id']}", json={"outcome": "won",
                                                     "victory_type": "Domination"})

    stats = client.get("/api/stats").json()
    assert stats["overall"]["won"] == 2
    assert stats["overall"]["lost"] == 1
    assert stats["overall"]["unrecorded"] == 0

    civs = {e["value"]: e for e in stats["by_dimension"]["civ"]["entries"]}
    assert (civs["Korea"]["won"], civs["Korea"]["lost"]) == (1, 1)
    assert civs["Rome"]["win_rate"] == 1.0
    assert stats["mean_winning_turn"] == 240


def test_builds_carry_the_tree_check(client, sample_config, stub_llm):
    """Always present, so the UI never has to guess; empty when there's nothing to say."""
    build = client.post("/api/generate", json={"config": sample_config}).json()
    assert isinstance(build["tree_issues"], list)
    fetched = client.get(f"/api/builds/{build['id']}").json()
    assert fetched["tree_issues"] == build["tree_issues"]


def test_a_cut_off_plan_is_saved_and_flagged(client, sample_config, monkeypatch):
    from backend import llm

    async def cut_off(system_prompt, user_prompt, max_tokens):
        return llm.Completion(text="## Civ & Leader\n**Korea**\n\n## Tech Path\n- Wri",
                              model="m", truncated=True)

    monkeypatch.setattr(llm, "complete", cut_off)
    build = client.post("/api/generate", json={"config": sample_config}).json()
    assert build["truncated"] is True
    # ...and it stays flagged in the archive.
    assert client.get(f"/api/builds/{build['id']}").json()["truncated"] is True


def test_a_finished_plan_is_not_flagged(client, sample_config, stub_llm):
    assert client.post("/api/generate", json={"config": sample_config}).json()["truncated"] is False


def test_a_decorated_header_is_tidied_before_saving(client, sample_config, monkeypatch):
    from backend import llm

    async def decorated(system_prompt, user_prompt, max_tokens):
        return llm.Completion(
            text="## Civ & Leader\n**Korea**\n\n## Timing Benchmarks (Standard speed)\n- T25: 3 cities",
            model="m",
        )

    monkeypatch.setattr(llm, "complete", decorated)
    plan = client.post("/api/generate", json={"config": sample_config}).json()["generated_plan"]
    assert "## Timing Benchmarks\n\nStandard speed.\n- T25: 3 cities" in plan


def test_the_speed_line_says_how_much_to_scale_when_the_game_data_knows(client, sample_config, stub_llm, monkeypatch):
    from backend import facts

    monkeypatch.setattr(facts, "game_speeds", lambda: {"Marathon": 300, "Standard": 100})
    client.post("/api/generate", json={"config": {**sample_config, "gameSpeed": "Marathon"}})
    assert ("- Game speed: Marathon (everything costs 300% of Standard, so multiply every "
            "Standard-speed turn count by 3, early milestones included: turn 30 → turn 90, "
            "turn 100 → turn 300)") in stub_llm[-1]["user"]
    client.post("/api/generate", json={"config": {**sample_config, "gameSpeed": "Standard"}})
    assert "- Game speed: Standard\n" in stub_llm[-1]["user"]      # nothing to scale


def test_the_speed_line_is_unchanged_without_game_data(client, sample_config, stub_llm, monkeypatch):
    from backend import facts

    monkeypatch.setattr(facts, "game_speeds", lambda: {})
    client.post("/api/generate", json={"config": {**sample_config, "gameSpeed": "Marathon"}})
    assert "- Game speed: Marathon\n" in stub_llm[-1]["user"]
