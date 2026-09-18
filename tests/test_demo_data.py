"""The demo data generator: safe to run, and it produces what it promises."""

from backend import config, db, demo_data


def test_it_refuses_to_write_into_the_real_database(tmp_path, monkeypatch):
    real = tmp_path / "real.db"
    monkeypatch.setattr(config, "db_path", lambda: real)
    assert demo_data.main(["--db", str(real)]) == 2
    assert not real.exists()


def test_it_writes_builds_with_a_mix_of_results(tmp_path):
    target = tmp_path / "demo.db"
    assert demo_data.main(["--db", str(target), "--count", "30", "--seed", "3"]) == 0

    original = config.db_path
    config.db_path = lambda: target
    try:
        db.close()
        stats = db.outcome_stats()["overall"]
    finally:
        db.close()
        config.db_path = original

    assert stats["builds"] == 30
    assert stats["won"] and stats["lost"]
    assert stats["unrecorded"] + stats["abandoned"] < 30


def test_the_same_seed_gives_the_same_data(tmp_path):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    demo_data.main(["--db", str(a), "--seed", "9"])
    demo_data.main(["--db", str(b), "--seed", "9"])
    import sqlite3
    rows = lambda p: sqlite3.connect(p).execute(
        "SELECT civ, primary_focus, outcome, end_turn FROM saved_builds ORDER BY id").fetchall()
    assert rows(a) == rows(b)
