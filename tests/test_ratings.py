"""Blind A/B rating: pairs from two eval runs, rated without knowing which is which."""

import json

import pytest

from backend import db


def _pair(experiment="exp", left_is_a=True, a="PLAN FROM A", b="PLAN FROM B"):
    return db.insert_rating_pair(
        experiment=experiment, brief_id="science-tall-korea",
        brief={"civ": "Korea", "config": {"gameSpeed": "Standard"}},
        label_a="single, effort medium", label_b="staged, effort medium",
        plan_a=a, plan_b=b, left_is_a=left_is_a,
    )


def test_the_pair_to_rate_says_nothing_about_which_setting_wrote_it(client):
    _pair()
    body = client.get("/api/ratings").json()
    shown = json.dumps(body["next"])
    assert "single" not in shown and "staged" not in shown
    assert set(body["next"]) == {"id", "experiment", "brief_id", "brief", "left", "right"}


@pytest.mark.parametrize("left_is_a, side, winner", [
    (True, "left", "single, effort medium"),
    (False, "left", "staged, effort medium"),     # sides are shuffled per pair
    (True, "right", "staged, effort medium"),
    (True, "tie", None),
])
def test_rating_a_side_credits_the_setting_behind_it(client, left_is_a, side, winner):
    pair_id = _pair(left_is_a=left_is_a)
    revealed = client.post(f"/api/ratings/{pair_id}", json={"side": side, "note": "clearer tempo"}).json()
    assert revealed["winner_label"] == winner
    assert {revealed["left_label"], revealed["right_label"]} == {"single, effort medium", "staged, effort medium"}


def test_the_sides_show_the_plans_the_shuffle_put_there(client):
    _pair(left_is_a=False)
    shown = client.get("/api/ratings").json()["next"]
    assert (shown["left"], shown["right"]) == ("PLAN FROM B", "PLAN FROM A")


def test_rated_pairs_leave_the_queue_and_count_in_the_summary(client):
    first, second = _pair(), _pair()
    client.post(f"/api/ratings/{first}", json={"side": "left"})
    body = client.get("/api/ratings").json()
    assert body["next"]["id"] == second
    [summary] = body["summary"]
    assert (summary["a_wins"], summary["b_wins"], summary["ties"], summary["unrated"]) == (1, 0, 0, 1)


def test_an_unknown_side_is_refused(client):
    pair_id = _pair()
    assert client.post(f"/api/ratings/{pair_id}", json={"side": "both"}).status_code in (400, 422)
    assert client.post("/api/ratings/999", json={"side": "tie"}).status_code == 404


@pytest.mark.parametrize("wins, losses, expected", [
    (0, 0, None),
    (5, 5, 1.0),
    (6, 0, 0.03125),      # six straight is unlikely by chance
    (4, 1, 0.375),        # four to one isn't enough yet
])
def test_the_sign_test(wins, losses, expected):
    result = db._sign_test(wins, losses)
    assert result == (None if expected is None else pytest.approx(expected))


def test_pairs_are_made_brief_by_brief_from_two_saved_runs(tmp_path, monkeypatch):
    from evals import pairs

    def run(name, pipeline, plans):
        (tmp_path / f"{name}.json").write_text(json.dumps({
            "started_at": "2026-09-19T08:00:00+00:00",
            "fingerprint": {"pipeline": pipeline, "reasoning_effort": "medium", "briefs_sha": "x"},
            "results": [{"brief": b, "attempt": 1, "plan": p} for b, p in plans.items()],
        }))

    run("20260101-000000", "single", {"science-tall-korea": "## tech path\n- a", "domination-wide": "A2"})
    run("20260102-000000", "staged", {"science-tall-korea": "## Tech Path\n- b", "religion-minimal": "B3"})
    monkeypatch.setattr(pairs, "RESULTS", tmp_path)
    db.migrate()

    assert pairs.make("20260101", "20260102", "single-vs-staged", None, None, seed=1) == 0
    rows = db.connect().execute("SELECT * FROM rating_pairs").fetchall()
    assert len(rows) == 1                                   # only the brief both runs have
    assert rows[0]["label_a"].startswith("single") and rows[0]["label_b"].startswith("staged")
    assert rows[0]["plan_a"] == "## Tech Path\n- a"         # headers tidied the same way
    with pytest.raises(SystemExit):                          # names aren't reused
        pairs.make("20260101", "20260102", "single-vs-staged", None, None, seed=1)
