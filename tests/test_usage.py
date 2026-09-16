"""Token and cost accounting: every model call gets logged, priced or not."""

import pytest


def _generate(client, sample_config, **overrides):
    payload = {
        "config": sample_config,
        "civ": "Korea",
        "city_philosophy": "Tall",
        "primary_focus": "Science",
        "posture": "No preference",
        "playstyle_text": "science",
    }
    payload.update(overrides)
    response = client.post("/api/generate", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_generate_records_tokens_and_cost(client, sample_config, stub_llm):
    build = _generate(client, sample_config)

    # Returned inline with the new build...
    assert build["usage"] == {
        "model": "anthropic/claude-sonnet-4-6",
        "prompt_tokens": 1182,
        "completion_tokens": 878,
        "cost_usd": 0.0167,
    }
    # ...and still there when the build is fetched later.
    assert client.get(f"/api/builds/{build['id']}").json()["usage"] == build["usage"]


def test_compare_calls_are_tracked_too(client, sample_config, stub_llm):
    first = _generate(client, sample_config, civ="Korea")
    second = _generate(client, sample_config, civ="Rome")

    compare = client.post(
        "/api/compare", json={"build_ids": [first["id"], second["id"]]}
    ).json()
    assert compare["usage"]["prompt_tokens"] == 3904
    assert compare["usage"]["cost_usd"] == 0.0177

    totals = client.get("/api/usage").json()
    assert totals["calls"] == 3                       # two generates + one compare
    assert totals["by_kind"]["generate"]["calls"] == 2
    assert totals["by_kind"]["compare"]["calls"] == 1
    # 0.0167 * 2 + 0.0177
    assert totals["cost_usd"] == pytest.approx(0.0511)
    assert totals["prompt_tokens"] == 1182 * 2 + 3904
    assert totals["has_unpriced_calls"] is False


def test_usage_starts_empty(client):
    totals = client.get("/api/usage").json()
    assert totals["calls"] == 0
    assert totals["cost_usd"] == 0.0
    assert totals["by_kind"] == {}
    assert totals["recent"] == []


def test_a_model_with_no_price_is_still_logged(
    client, sample_config, stub_llm_without_usage
):
    """An unpriced or usage-less provider must not break generation or accounting."""
    build = _generate(client, sample_config)

    assert build["usage"] == {
        "model": "ollama/llama3.1",
        "prompt_tokens": None,
        "completion_tokens": None,
        "cost_usd": None,
    }

    totals = client.get("/api/usage").json()
    assert totals["calls"] == 1
    assert totals["cost_usd"] == 0.0          # nothing known to add up
    assert totals["has_unpriced_calls"] is True   # so the UI can hedge the total


def test_recent_calls_are_newest_first_and_name_their_build(
    client, sample_config, stub_llm
):
    build = _generate(client, sample_config)
    client.post("/api/compare", json={"build_ids": [build["id"], build["id"]]})

    recent = client.get("/api/usage").json()["recent"]
    assert [r["kind"] for r in recent] == ["generate"]
    assert recent[0]["build_title"] == build["title"]
    assert recent[0]["build_id"] == build["id"]


def test_deleting_a_build_keeps_its_cost_on_the_books(
    client, sample_config, stub_llm
):
    """You still spent the money, so the spend record outlives the build."""
    build = _generate(client, sample_config)
    assert client.delete(f"/api/builds/{build['id']}").status_code == 200

    totals = client.get("/api/usage").json()
    assert totals["calls"] == 1
    assert totals["cost_usd"] == pytest.approx(0.0167)
    # The row survives, orphaned rather than deleted.
    assert totals["recent"][0]["build_id"] is None
