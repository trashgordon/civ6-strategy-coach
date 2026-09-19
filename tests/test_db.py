"""Schema versioning — people `git pull` updates and expect saved builds to survive."""

import sqlite3

from backend import db



def _legacy_build(conn, *, title, civ, plan, playstyle_text="tech", **extra):
    """Insert a row using only the v1 columns, as a pre-upgrade release would have."""
    with conn:
        cursor = conn.execute(
            "INSERT INTO saved_builds (created_at, title, civ, city_philosophy, "
            "primary_focus, playstyle_text, generated_plan) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2026-01-01T00:00:00+00:00", title, civ, extra.get("city_philosophy", "Tall"),
             extra.get("primary_focus", "Science"), playstyle_text, plan),
        )
    return {"id": cursor.lastrowid}

def test_migrate_creates_the_schema_and_stamps_the_version():
    assert db.migrate() == db.CURRENT_VERSION
    conn = db.connect()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.CURRENT_VERSION

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(saved_builds)")}
    assert columns == {
        "id", "created_at", "title", "ruleset", "difficulty", "map_type",
        "config_json", "civ", "city_philosophy", "primary_focus", "posture",
        "playstyle_text", "generated_plan", "notes",
        "outcome", "victory_type", "end_turn", "recommended_civ", "truncated",
        "decisions_json",
    }


def test_migrate_is_idempotent_and_keeps_existing_rows():
    db.migrate()
    saved = db.insert_build(
        title="Korea — Science",
        config_dict={"ruleset": "Gathering Storm", "mapType": "Pangaea"},
        civ="Korea",
        city_philosophy="Tall",
        primary_focus="Science",
        posture="No preference",
        playstyle_text="tech and turtle",
        generated_plan="## Civ & Leader recommendation\n**Korea**",
    )

    # Simulate a `git pull` + restart: migrate runs again over a populated database.
    assert db.migrate() == db.CURRENT_VERSION
    assert db.get_build(saved["id"])["title"] == "Korea — Science"


def test_get_builds_preserves_the_order_the_user_picked():
    db.migrate()
    ids = [
        db.insert_build(
            title=f"Build {i}", config_dict={}, civ=f"Civ{i}", city_philosophy="",
            primary_focus="", posture="", playstyle_text="", generated_plan="",
        )["id"]
        for i in range(3)
    ]

    assert [b["id"] for b in db.get_builds([ids[2], ids[0]])] == [ids[2], ids[0]]
    # Missing ids are skipped rather than raising.
    assert [b["id"] for b in db.get_builds([ids[1], 9999])] == [ids[1]]
    assert db.get_builds([]) == []


def test_malformed_config_json_does_not_break_reads():
    db.migrate()
    conn = db.connect()
    with conn:
        conn.execute(
            "INSERT INTO saved_builds (created_at, config_json) VALUES ('2026-01-01', 'not json')"
        )
    row_id = conn.execute("SELECT id FROM saved_builds").fetchone()["id"]
    assert db.get_build(row_id)["config"] == {}


def test_distinct_values_rejects_an_arbitrary_column():
    db.migrate()
    try:
        db.distinct_values("generated_plan")
    except ValueError as exc:
        assert "filterable" in str(exc)
    else:
        raise AssertionError("expected a ValueError")


def test_a_v1_database_upgrades_to_v2_without_losing_builds():
    """The `git pull` case: someone's existing archive meets the new api_calls table."""
    conn = db.connect()

    # Stand up a database at v1 exactly as the previous release left it.
    with conn:
        conn.executescript(db.SCHEMA_V1)
        conn.execute("PRAGMA user_version = 1")
    saved = _legacy_build(
        conn, title="Korea — Science", civ="Korea", playstyle_text="tech and turtle",
        plan="## Plan\n**Korea**",
    )
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    tables_before = {
        r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "api_calls" not in tables_before

    # Now upgrade, the way startup does.
    assert db.migrate() == db.CURRENT_VERSION

    # The pre-existing build is untouched...
    still_there = db.get_build(saved["id"])
    assert still_there["title"] == "Korea — Science"
    assert still_there["playstyle_text"] == "tech and turtle"
    # ...the new table exists...
    assert "api_calls" in {
        r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    # ...and a build that predates tracking simply reports no usage.
    assert db.usage_for_build(saved["id"]) is None
    assert db.usage_totals()["calls"] == 0


def test_usage_totals_ignore_nulls_but_flag_them():
    db.migrate()
    db.insert_api_call(kind=db.GENERATE, model="m", prompt_tokens=100,
                       completion_tokens=50, cost_usd=0.01)
    db.insert_api_call(kind=db.GENERATE, model="local", prompt_tokens=None,
                       completion_tokens=None, cost_usd=None)

    totals = db.usage_totals()
    assert totals["calls"] == 2
    assert totals["prompt_tokens"] == 100          # the NULL doesn't poison the sum
    assert totals["cost_usd"] == 0.01
    assert totals["has_unpriced_calls"] is True


def test_a_v2_database_gains_the_cache_columns_without_losing_calls():
    """Someone who used the cost-tracking release before prompt caching existed."""
    conn = db.connect()
    with conn:
        conn.executescript(db.SCHEMA_V1)
        conn.executescript(db.SCHEMA_V2)
        conn.execute("PRAGMA user_version = 2")
        conn.execute(
            "INSERT INTO api_calls (created_at, kind, model, prompt_tokens, "
            "completion_tokens, cost_usd) VALUES ('2026-01-01', 'generate', 'm', 10, 5, 0.01)"
        )

    assert db.migrate() == db.CURRENT_VERSION

    columns = {r["name"] for r in conn.execute("PRAGMA table_info(api_calls)")}
    assert {"cache_write_tokens", "cache_read_tokens"} <= columns

    # The pre-existing call survives, with the new columns simply unknown.
    totals = db.usage_totals()
    assert totals["calls"] == 1
    assert totals["cost_usd"] == 0.01
    assert totals["cache_read_tokens"] == 0


def test_a_v3_database_gains_notes_without_losing_builds():
    """The campaign journal arriving for someone who already has an archive."""
    conn = db.connect()
    with conn:
        conn.executescript(db.SCHEMA_V1)
        conn.executescript(db.SCHEMA_V2)
        conn.executescript(db.SCHEMA_V3)
        conn.execute("PRAGMA user_version = 3")
    saved = _legacy_build(
        conn, title="Korea — Science", civ="Korea", plan="## Civ & Leader\n**Korea**",
    )

    assert db.migrate() == db.CURRENT_VERSION

    build = db.get_build(saved["id"])
    assert build["title"] == "Korea — Science"
    assert build["notes"] == ""          # new column, sensible default


def test_title_and_notes_update_independently():
    db.migrate()
    build = db.insert_build(
        title="Original", config_dict={}, civ="", city_philosophy="", primary_focus="",
        posture="", playstyle_text="", generated_plan="plan",
    )

    only_notes = db.update_build(build["id"], notes="Turn 40: forward-settled by Rome")
    assert only_notes["notes"] == "Turn 40: forward-settled by Rome"
    assert only_notes["title"] == "Original"      # untouched

    only_title = db.update_build(build["id"], title="Renamed")
    assert only_title["title"] == "Renamed"
    assert only_title["notes"] == "Turn 40: forward-settled by Rome"   # untouched


def test_a_v4_database_gains_outcome_columns_without_losing_builds():
    conn = db.connect()
    with conn:
        for schema in (db.SCHEMA_V1, db.SCHEMA_V2, db.SCHEMA_V3, db.SCHEMA_V4):
            conn.executescript(schema)
        conn.execute("PRAGMA user_version = 4")
    saved = _legacy_build(
        conn, title="Korea — Science", civ="Korea", plan="## Civ & Leader\n**Korea**",
    )
    with conn:
        conn.execute("UPDATE saved_builds SET notes = 'turn 40 notes' WHERE id = ?",
                     (saved["id"],))

    assert db.migrate() == db.CURRENT_VERSION

    build = db.get_build(saved["id"])
    assert build["title"] == "Korea — Science"
    assert build["notes"] == "turn 40 notes"
    # New columns default to "not recorded", not to a guess.
    assert build["outcome"] == ""
    assert build["victory_type"] == ""
    assert build["end_turn"] is None


def _won(civ, focus, turn=None, outcome="won", victory="Science"):
    build = db.insert_build(
        title=f"{civ} — {focus}", config_dict={"mapType": "Pangaea"}, civ=civ,
        city_philosophy="Tall", primary_focus=focus, posture="", playstyle_text="",
        generated_plan="plan",
    )
    db.update_build(build["id"], outcome=outcome, victory_type=victory, end_turn=turn)
    return build["id"]


def test_stats_report_counts_alongside_every_rate():
    db.migrate()
    _won("Korea", "Science", turn=247)
    _won("Korea", "Science", turn=210)
    _won("Korea", "Science", outcome="lost", victory="")
    _won("Rome", "Domination", outcome="abandoned", victory="")
    db.insert_build(
        title="unlogged", config_dict={}, civ="Maori", city_philosophy="",
        primary_focus="Culture", posture="", playstyle_text="", generated_plan="p",
    )

    stats = db.outcome_stats()
    overall = stats["overall"]
    assert (overall["won"], overall["lost"], overall["abandoned"]) == (2, 1, 1)
    assert overall["unrecorded"] == 1
    assert overall["win_rate"] == round(2 / 3, 3)   # abandoned doesn't count either way

    korea = next(
        e for e in stats["by_dimension"]["civ"]["entries"] if e["value"] == "Korea"
    )
    assert (korea["won"], korea["lost"]) == (2, 1)
    assert stats["victories"] == [{"victory_type": "Science", "count": 2}]
    assert stats["mean_winning_turn"] == round((247 + 210) / 2)
    assert stats["fastest_win_turn"] == 210


def test_stats_ignore_no_preference_as_a_dimension():
    db.migrate()
    build = db.insert_build(
        title="x", config_dict={}, civ="", city_philosophy="No preference",
        primary_focus="No preference", posture="", playstyle_text="", generated_plan="p",
    )
    db.update_build(build["id"], outcome="won")

    stats = db.outcome_stats()
    assert stats["by_dimension"]["civ"]["entries"] == []
    assert stats["by_dimension"]["city_philosophy"]["entries"] == []
    # It still counts towards the overall record.
    assert stats["overall"]["won"] == 1


def test_an_end_turn_can_be_cleared():
    db.migrate()
    build = db.insert_build(
        title="x", config_dict={}, civ="Korea", city_philosophy="", primary_focus="",
        posture="", playstyle_text="", generated_plan="p",
    )
    db.update_build(build["id"], end_turn=247)
    assert db.get_build(build["id"])["end_turn"] == 247

    db.update_build(build["id"], clear_end_turn=True)
    assert db.get_build(build["id"])["end_turn"] is None


def test_dimensions_omit_values_with_nothing_decided():
    """An abandoned-only civ says nothing about what wins."""
    db.migrate()
    abandoned = db.insert_build(
        title="x", config_dict={}, civ="Ethiopia", city_philosophy="", primary_focus="",
        posture="", playstyle_text="", generated_plan="p",
    )
    db.update_build(abandoned["id"], outcome="abandoned")
    decided = db.insert_build(
        title="y", config_dict={}, civ="Korea", city_philosophy="", primary_focus="",
        posture="", playstyle_text="", generated_plan="p",
    )
    db.update_build(decided["id"], outcome="won")

    civs = [e["value"] for e in db.outcome_stats()["by_dimension"]["civ"]["entries"]]
    assert civs == ["Korea"]
    # Still counted in the overall tally.
    assert db.outcome_stats()["overall"]["abandoned"] == 1


def test_the_coachs_pick_counts_as_the_civ_played():
    """Most briefings leave the civ to the coach; stats should still know who you played."""
    db.migrate()
    picked = db.insert_build(
        title="x", config_dict={}, civ="", city_philosophy="", primary_focus="",
        posture="", playstyle_text="", generated_plan="## Civ & Leader\n**Korea — Seondeok**",
    )
    chosen = db.insert_build(
        title="y", config_dict={}, civ="Rome", city_philosophy="", primary_focus="",
        posture="", playstyle_text="", generated_plan="## Civ & Leader\n**Korea**",
    )
    assert picked["recommended_civ"] == "Korea"
    assert picked["played_civ"] == "Korea"
    # A civ the player chose wins over whatever the plan says.
    assert chosen["played_civ"] == "Rome"

    db.update_build(picked["id"], outcome="won")
    db.update_build(chosen["id"], outcome="lost")
    civs = {e["value"] for e in db.outcome_stats()["by_dimension"]["civ"]["entries"]}
    assert civs == {"Korea", "Rome"}
    assert [b["id"] for b in db.list_builds(civ="Korea")] == [picked["id"]]
    assert set(db.distinct_values("civ")) == {"Korea", "Rome"}


def test_a_v5_database_backfills_the_coachs_pick_from_saved_plans():
    conn = db.connect()
    with conn:
        for schema in (db.SCHEMA_V1, db.SCHEMA_V2, db.SCHEMA_V3, db.SCHEMA_V4, db.SCHEMA_V5):
            conn.executescript(schema)
        conn.execute("PRAGMA user_version = 5")
    korea = _legacy_build(conn, title="a", civ="", plan="## Civ & Leader\n**Korea — Seondeok**")
    prose = _legacy_build(conn, title="b", civ="", plan="p")

    assert db.migrate() == db.CURRENT_VERSION
    assert db.get_build(korea["id"])["recommended_civ"] == "Korea"
    # Nothing recognisable in the plan: leave it blank rather than guess.
    assert db.get_build(prose["id"])["recommended_civ"] == ""
