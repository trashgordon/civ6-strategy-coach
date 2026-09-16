"""SQLite storage: one file, one table.

Schema versioning is deliberately tiny — a `PRAGMA user_version` check at startup runs
whatever ALTER TABLEs are missing and bumps the version. People will `git pull` updates
and expect their existing saved builds to survive, so every future schema change gets a
new entry in MIGRATIONS rather than an edit to an existing one.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import config

_local = threading.local()

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS saved_builds (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at       TEXT    NOT NULL,
    title            TEXT    NOT NULL DEFAULT '',
    ruleset          TEXT    NOT NULL DEFAULT '',
    difficulty       TEXT    NOT NULL DEFAULT '',
    map_type         TEXT    NOT NULL DEFAULT '',
    config_json      TEXT    NOT NULL DEFAULT '{}',
    civ              TEXT    NOT NULL DEFAULT '',
    city_philosophy  TEXT    NOT NULL DEFAULT '',
    primary_focus    TEXT    NOT NULL DEFAULT '',
    posture          TEXT    NOT NULL DEFAULT '',
    playstyle_text   TEXT    NOT NULL DEFAULT '',
    generated_plan   TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_saved_builds_created_at ON saved_builds (created_at DESC);
"""

# version -> SQL to reach that version. Append only.
MIGRATIONS: list[tuple[int, str]] = [
    (1, SCHEMA_V1),
]

CURRENT_VERSION = MIGRATIONS[-1][0]


def connect() -> sqlite3.Connection:
    """One connection per thread; FastAPI runs sync handlers in a threadpool."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        path = config.db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        _local.conn = conn
    return conn


def close() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def migrate() -> int:
    """Bring the database up to CURRENT_VERSION. Safe to call on every startup."""
    conn = connect()
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for target, sql in MIGRATIONS:
        if version >= target:
            continue
        with conn:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {target}")
        version = target
    return version


def _row_to_build(row: sqlite3.Row, include_plan: bool = True) -> dict[str, Any]:
    try:
        parsed_config = json.loads(row["config_json"] or "{}")
    except json.JSONDecodeError:
        parsed_config = {}

    build = {
        "id": row["id"],
        "created_at": row["created_at"],
        "title": row["title"],
        "ruleset": row["ruleset"],
        "difficulty": row["difficulty"],
        "map_type": row["map_type"],
        "config": parsed_config,
        "civ": row["civ"],
        "city_philosophy": row["city_philosophy"],
        "primary_focus": row["primary_focus"],
        "posture": row["posture"],
        "playstyle_text": row["playstyle_text"],
    }
    if include_plan:
        build["generated_plan"] = row["generated_plan"]
    return build


def insert_build(
    *,
    title: str,
    config_dict: dict[str, Any],
    civ: str,
    city_philosophy: str,
    primary_focus: str,
    posture: str,
    playstyle_text: str,
    generated_plan: str,
) -> dict[str, Any]:
    conn = connect()
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO saved_builds (
                created_at, title, ruleset, difficulty, map_type, config_json,
                civ, city_philosophy, primary_focus, posture, playstyle_text, generated_plan
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                title,
                config_dict.get("ruleset", "") or "",
                config_dict.get("difficulty", "") or "",
                config_dict.get("mapType", "") or "",
                json.dumps(config_dict),
                civ or "",
                city_philosophy or "",
                primary_focus or "",
                posture or "",
                playstyle_text or "",
                generated_plan or "",
            ),
        )
    return get_build(cursor.lastrowid)  # type: ignore[arg-type]


def list_builds(
    *,
    query: str = "",
    civ: str = "",
    primary_focus: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Newest first. `query` is a substring match across the fields worth searching."""
    sql = ["SELECT * FROM saved_builds"]
    where: list[str] = []
    params: list[Any] = []

    if query.strip():
        needle = f"%{query.strip()}%"
        where.append(
            "(title LIKE ? OR civ LIKE ? OR playstyle_text LIKE ? OR generated_plan LIKE ?)"
        )
        params.extend([needle] * 4)
    if civ.strip():
        where.append("civ = ?")
        params.append(civ.strip())
    if primary_focus.strip():
        where.append("primary_focus = ?")
        params.append(primary_focus.strip())

    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY created_at DESC, id DESC LIMIT ?")
    params.append(limit)

    rows = connect().execute(" ".join(sql), params).fetchall()
    # The archive list doesn't need the full plan text; the detail view fetches it.
    return [_row_to_build(row, include_plan=False) for row in rows]


def get_build(build_id: int) -> dict[str, Any] | None:
    row = connect().execute("SELECT * FROM saved_builds WHERE id = ?", (build_id,)).fetchone()
    return _row_to_build(row) if row else None


def get_builds(build_ids: Iterable[int]) -> list[dict[str, Any]]:
    """Returns builds in the order the ids were given, skipping ones that don't exist."""
    ids = list(build_ids)
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = connect().execute(
        f"SELECT * FROM saved_builds WHERE id IN ({placeholders})", ids
    ).fetchall()
    by_id = {row["id"]: _row_to_build(row) for row in rows}
    return [by_id[i] for i in ids if i in by_id]


def update_title(build_id: int, title: str) -> dict[str, Any] | None:
    conn = connect()
    with conn:
        conn.execute("UPDATE saved_builds SET title = ? WHERE id = ?", (title, build_id))
    return get_build(build_id)


def delete_build(build_id: int) -> bool:
    conn = connect()
    with conn:
        cursor = conn.execute("DELETE FROM saved_builds WHERE id = ?", (build_id,))
    return cursor.rowcount > 0


def distinct_values(column: str) -> list[str]:
    """Used to populate the archive's filter dropdowns with only what's actually saved."""
    if column not in {"civ", "primary_focus", "posture", "city_philosophy", "ruleset"}:
        raise ValueError(f"not a filterable column: {column}")
    rows = connect().execute(
        f"SELECT DISTINCT {column} AS value FROM saved_builds "
        f"WHERE {column} != '' ORDER BY value COLLATE NOCASE"
    ).fetchall()
    return [row["value"] for row in rows]


def db_file() -> Path:
    return config.db_path()
