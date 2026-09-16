"""Schema versioning — people `git pull` updates and expect saved builds to survive."""

import sqlite3

from backend import db


def test_migrate_creates_the_schema_and_stamps_the_version():
    assert db.migrate() == db.CURRENT_VERSION
    conn = db.connect()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.CURRENT_VERSION

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(saved_builds)")}
    assert columns == {
        "id", "created_at", "title", "ruleset", "difficulty", "map_type",
        "config_json", "civ", "city_philosophy", "primary_focus", "posture",
        "playstyle_text", "generated_plan",
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
