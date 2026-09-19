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

SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS api_calls (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at        TEXT    NOT NULL,
    kind              TEXT    NOT NULL,          -- 'generate' | 'compare'
    build_id          INTEGER,                   -- set for 'generate', NULL for 'compare'
    model             TEXT    NOT NULL DEFAULT '',
    prompt_tokens     INTEGER,                   -- NULL when the provider didn't report
    completion_tokens INTEGER,
    cost_usd          REAL,                      -- NULL when the model isn't priced
    FOREIGN KEY (build_id) REFERENCES saved_builds (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_api_calls_created_at ON api_calls (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_calls_build_id ON api_calls (build_id);
"""

# Prompt-cache accounting. Nullable, so every row written before v3 stays valid.
SCHEMA_V3 = """
ALTER TABLE api_calls ADD COLUMN cache_write_tokens INTEGER;
ALTER TABLE api_calls ADD COLUMN cache_read_tokens INTEGER;
"""

# The campaign journal: free text the player edits as the game actually plays out.
SCHEMA_V4 = """
ALTER TABLE saved_builds ADD COLUMN notes TEXT NOT NULL DEFAULT '';
"""

# How the game actually went. Empty outcome means "not recorded yet", which is
# deliberately distinct from "abandoned" — most builds will never be logged.
SCHEMA_V5 = """
ALTER TABLE saved_builds ADD COLUMN outcome TEXT NOT NULL DEFAULT '';
ALTER TABLE saved_builds ADD COLUMN victory_type TEXT NOT NULL DEFAULT '';
ALTER TABLE saved_builds ADD COLUMN end_turn INTEGER;
"""

# The civ the coach recommended. Most briefings leave the civ to the coach, so without
# this a build's `civ` is blank and it vanishes from every per-civ breakdown.
SCHEMA_V6 = """
ALTER TABLE saved_builds ADD COLUMN recommended_civ TEXT NOT NULL DEFAULT '';
"""

# Set when the model hit its output limit and the plan is missing its last sections.
SCHEMA_V7 = """
ALTER TABLE saved_builds ADD COLUMN truncated INTEGER NOT NULL DEFAULT 0;
"""

# The staged pipeline's checked decisions (JSON), kept beside the prose they produced.
SCHEMA_V8 = """
ALTER TABLE saved_builds ADD COLUMN decisions_json TEXT NOT NULL DEFAULT '';
"""

# Blind A/B ratings: two plans for the same brief from two settings, shown unlabelled.
# `left_is_a` fixes which side each plan appears on, so a reload can't reshuffle it.
SCHEMA_V9 = """
CREATE TABLE IF NOT EXISTS rating_pairs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    experiment  TEXT    NOT NULL,
    brief_id    TEXT    NOT NULL DEFAULT '',
    brief_json  TEXT    NOT NULL DEFAULT '{}',
    label_a     TEXT    NOT NULL,
    label_b     TEXT    NOT NULL,
    plan_a      TEXT    NOT NULL,
    plan_b      TEXT    NOT NULL,
    left_is_a   INTEGER NOT NULL,
    verdict     TEXT    NOT NULL DEFAULT '',   -- '' | 'a' | 'b' | 'tie'
    note        TEXT    NOT NULL DEFAULT '',
    rated_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_rating_pairs_experiment ON rating_pairs (experiment);
"""

# The civ a build was actually played as: the player's pick when they made one,
# otherwise the coach's. Used wherever a build is grouped, filtered or shown by civ.
PLAYED_CIV = "COALESCE(NULLIF(civ, ''), NULLIF(recommended_civ, ''), '')"

# version -> SQL to reach that version. Append only.
MIGRATIONS: list[tuple[int, str]] = [
    (1, SCHEMA_V1),
    (2, SCHEMA_V2),
    (3, SCHEMA_V3),
    (4, SCHEMA_V4),
    (5, SCHEMA_V5),
    (6, SCHEMA_V6),
    (7, SCHEMA_V7),
    (8, SCHEMA_V8),
    (9, SCHEMA_V9),
]

OUTCOMES = ("won", "lost", "abandoned")
VICTORY_TYPES = ("Science", "Culture", "Domination", "Religious", "Diplomatic", "Score")

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


def recommended_civ_from_plan(plan: str) -> str:
    """The coach's pick, but only when it's a civ we recognise — never a prose guess."""
    from .gamedata import match_civ  # local imports: neither module needs db
    from .titles import civ_from_plan

    return match_civ(civ_from_plan(plan)) or ""


def _backfill_recommended_civ(conn: sqlite3.Connection) -> None:
    """Read the coach's pick back out of every plan saved before v6 stored it."""
    rows = conn.execute(
        "SELECT id, generated_plan FROM saved_builds WHERE recommended_civ = ''"
    ).fetchall()
    for row in rows:
        civ = recommended_civ_from_plan(row["generated_plan"] or "")
        if civ:
            conn.execute(
                "UPDATE saved_builds SET recommended_civ = ? WHERE id = ?", (civ, row["id"])
            )


# Data changes that have to run in Python, once, straight after a version's SQL.
BACKFILLS = {6: _backfill_recommended_civ}


def migrate() -> int:
    """Bring the database up to CURRENT_VERSION. Safe to call on every startup."""
    conn = connect()
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for target, sql in MIGRATIONS:
        if version >= target:
            continue
        with conn:
            conn.executescript(sql)
            if target in BACKFILLS:
                BACKFILLS[target](conn)
            conn.execute(f"PRAGMA user_version = {target}")
        version = target
    return version


def _decisions(row: sqlite3.Row) -> dict | None:
    raw = row["decisions_json"] if "decisions_json" in row.keys() else ""
    try:
        value = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


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
        "recommended_civ": row["recommended_civ"] if "recommended_civ" in row.keys() else "",
        "notes": row["notes"] if "notes" in row.keys() else "",
        "outcome": row["outcome"] if "outcome" in row.keys() else "",
        "victory_type": row["victory_type"] if "victory_type" in row.keys() else "",
        "end_turn": row["end_turn"] if "end_turn" in row.keys() else None,
        "truncated": bool(row["truncated"]) if "truncated" in row.keys() else False,
        "decisions": _decisions(row),
    }
    if include_plan:
        build["generated_plan"] = row["generated_plan"]
    build["played_civ"] = build["civ"] or build["recommended_civ"]
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
    recommended_civ: str | None = None,
    truncated: bool = False,
    decisions: dict | None = None,
) -> dict[str, Any]:
    if recommended_civ is None:
        recommended_civ = recommended_civ_from_plan(generated_plan or "")
    conn = connect()
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO saved_builds (
                created_at, title, ruleset, difficulty, map_type, config_json,
                civ, city_philosophy, primary_focus, posture, playstyle_text, generated_plan,
                recommended_civ, truncated, decisions_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                recommended_civ or "",
                int(bool(truncated)),
                json.dumps(decisions, ensure_ascii=False) if decisions else "",
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
        where.append(f"{PLAYED_CIV} = ?")
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


def update_build(
    build_id: int,
    *,
    title: str | None = None,
    notes: str | None = None,
    outcome: str | None = None,
    victory_type: str | None = None,
    end_turn: int | None = None,
    clear_end_turn: bool = False,
) -> dict[str, Any] | None:
    """Update whichever fields were supplied. Anything left None is untouched.

    `clear_end_turn` exists because None already means "don't touch" — without it there
    would be no way to unset a turn count that was entered by mistake.
    """
    assignments: list[str] = []
    params: list[Any] = []
    if title is not None:
        assignments.append("title = ?")
        params.append(title)
    if notes is not None:
        assignments.append("notes = ?")
        params.append(notes)
    if outcome is not None:
        assignments.append("outcome = ?")
        params.append(outcome)
    if victory_type is not None:
        assignments.append("victory_type = ?")
        params.append(victory_type)
    if clear_end_turn:
        assignments.append("end_turn = NULL")
    elif end_turn is not None:
        assignments.append("end_turn = ?")
        params.append(end_turn)
    if not assignments:
        return get_build(build_id)

    params.append(build_id)
    conn = connect()
    with conn:
        conn.execute(
            f"UPDATE saved_builds SET {', '.join(assignments)} WHERE id = ?", params
        )
    return get_build(build_id)


def update_title(build_id: int, title: str) -> dict[str, Any] | None:
    return update_build(build_id, title=title)


def delete_build(build_id: int) -> bool:
    conn = connect()
    with conn:
        cursor = conn.execute("DELETE FROM saved_builds WHERE id = ?", (build_id,))
    return cursor.rowcount > 0


def distinct_values(column: str) -> list[str]:
    """Used to populate the archive's filter dropdowns with only what's actually saved."""
    if column not in {"civ", "primary_focus", "posture", "city_philosophy", "ruleset"}:
        raise ValueError(f"not a filterable column: {column}")
    expression = PLAYED_CIV if column == "civ" else column
    rows = connect().execute(
        f"SELECT DISTINCT {expression} AS value FROM saved_builds "
        f"WHERE {expression} != '' ORDER BY value COLLATE NOCASE"
    ).fetchall()
    return [row["value"] for row in rows]


def db_file() -> Path:
    return config.db_path()


# --------------------------------------------------------------------- api usage

GENERATE = "generate"
COMPARE = "compare"


def insert_api_call(
    *,
    kind: str,
    model: str,
    build_id: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cost_usd: float | None = None,
    cache_write_tokens: int | None = None,
    cache_read_tokens: int | None = None,
) -> int:
    """Record one model call. Never raises on a cost we couldn't determine — the
    columns are nullable precisely so an unpriced model still gets logged."""
    conn = connect()
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO api_calls (
                created_at, kind, build_id, model,
                prompt_tokens, completion_tokens, cost_usd,
                cache_write_tokens, cache_read_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (created_at, kind, build_id, model or "",
             prompt_tokens, completion_tokens, cost_usd,
             cache_write_tokens, cache_read_tokens),
        )
    return cursor.lastrowid  # type: ignore[return-value]


def _usage_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "calls": row["calls"] or 0,
        "prompt_tokens": row["prompt_tokens"] or 0,
        "completion_tokens": row["completion_tokens"] or 0,
        "cost_usd": row["cost_usd"] or 0.0,
        "cache_write_tokens": row["cache_write_tokens"] or 0,
        "cache_read_tokens": row["cache_read_tokens"] or 0,
        # True when at least one call had no price, so a total can be shown as "at least".
        "has_unpriced_calls": bool(row["unpriced"]),
    }


_USAGE_SELECT = """
SELECT COUNT(*)                                   AS calls,
       COALESCE(SUM(prompt_tokens), 0)            AS prompt_tokens,
       COALESCE(SUM(completion_tokens), 0)        AS completion_tokens,
       COALESCE(SUM(cost_usd), 0.0)               AS cost_usd,
       COALESCE(SUM(cache_write_tokens), 0)       AS cache_write_tokens,
       COALESCE(SUM(cache_read_tokens), 0)        AS cache_read_tokens,
       SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END) AS unpriced
FROM api_calls
"""


def usage_totals() -> dict[str, Any]:
    """Lifetime spend, plus a breakdown by call kind."""
    conn = connect()
    overall = _usage_row(conn.execute(_USAGE_SELECT).fetchone())

    grouped = _USAGE_SELECT.replace("SELECT COUNT(*)", "SELECT kind, COUNT(*)", 1)
    by_kind = {
        row["kind"]: _usage_row(row)
        for row in conn.execute(f"{grouped} GROUP BY kind").fetchall()
    }

    overall["by_kind"] = by_kind
    return overall


def usage_for_build(build_id: int) -> dict[str, Any] | None:
    """What producing this build cost, summed over every call it took (the staged
    pipeline makes two or more). None if it predates tracking."""
    row = connect().execute(
        """
        SELECT COUNT(*) AS calls, MAX(model) AS model,
               SUM(prompt_tokens) AS prompt_tokens,
               SUM(completion_tokens) AS completion_tokens,
               SUM(cost_usd) AS cost_usd
        FROM api_calls
        WHERE build_id = ? AND kind = ?
        """,
        (build_id, GENERATE),
    ).fetchone()
    if row is None or not row["calls"]:
        return None
    return {
        "model": row["model"],
        "prompt_tokens": row["prompt_tokens"],
        "completion_tokens": row["completion_tokens"],
        "cost_usd": row["cost_usd"],
        "calls": row["calls"],
    }


def recent_api_calls(limit: int = 50) -> list[dict[str, Any]]:
    rows = connect().execute(
        """
        SELECT a.id, a.created_at, a.kind, a.build_id, a.model,
               a.prompt_tokens, a.completion_tokens, a.cost_usd,
               b.title AS build_title
        FROM api_calls a
        LEFT JOIN saved_builds b ON b.id = a.build_id
        ORDER BY a.id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


# ------------------------------------------------------------------- outcomes

# Dimensions the stats view can break results down by. Keyed by the column, since
# these are all plain columns on saved_builds.
# (key in the API response, SQL expression to group by, label)
STAT_DIMENSIONS = (
    ("civ", PLAYED_CIV, "Civ played"),
    ("primary_focus", "primary_focus", "Focus"),
    ("city_philosophy", "city_philosophy", "City philosophy"),
    ("posture", "posture", "Posture"),
    ("map_type", "map_type", "Map"),
    ("difficulty", "difficulty", "Difficulty"),
)

_UNSET = ("", "No preference")


def _rate(won: int, lost: int) -> float | None:
    """Win rate over decided games. None when nothing has been decided yet."""
    decided = won + lost
    return round(won / decided, 3) if decided else None


def outcome_stats() -> dict[str, Any]:
    """Win/loss records overall and broken down by each dimension.

    Counts are reported alongside every rate on purpose: with a handful of games a
    percentage on its own invites reading signal into a 1-0 record.
    """
    conn = connect()

    totals = conn.execute(
        """
        SELECT
            COUNT(*)                                                   AS builds,
            SUM(CASE WHEN outcome = 'won' THEN 1 ELSE 0 END)           AS won,
            SUM(CASE WHEN outcome = 'lost' THEN 1 ELSE 0 END)          AS lost,
            SUM(CASE WHEN outcome = 'abandoned' THEN 1 ELSE 0 END)     AS abandoned,
            SUM(CASE WHEN outcome = '' THEN 1 ELSE 0 END)              AS unrecorded
        FROM saved_builds
        """
    ).fetchone()

    overall = {
        "builds": totals["builds"] or 0,
        "won": totals["won"] or 0,
        "lost": totals["lost"] or 0,
        "abandoned": totals["abandoned"] or 0,
        "unrecorded": totals["unrecorded"] or 0,
    }
    overall["win_rate"] = _rate(overall["won"], overall["lost"])

    by_dimension: dict[str, Any] = {}
    for key, column, label in STAT_DIMENSIONS:
        rows = conn.execute(
            f"""
            SELECT {column} AS value,
                   SUM(CASE WHEN outcome = 'won' THEN 1 ELSE 0 END)       AS won,
                   SUM(CASE WHEN outcome = 'lost' THEN 1 ELSE 0 END)      AS lost,
                   SUM(CASE WHEN outcome = 'abandoned' THEN 1 ELSE 0 END) AS abandoned,
                   COUNT(*)                                               AS builds
            FROM saved_builds
            WHERE outcome != ''
            GROUP BY {column}
            """
        ).fetchall()

        entries = []
        for row in rows:
            value = (row["value"] or "").strip()
            if value in _UNSET:
                # "No preference" isn't a strategy, so it isn't a row worth ranking.
                continue
            if not (row["won"] or 0) and not (row["lost"] or 0):
                # Only abandoned games under this value — nothing decided, so it says
                # nothing about what wins.
                continue
            entries.append(
                {
                    "value": value,
                    "won": row["won"] or 0,
                    "lost": row["lost"] or 0,
                    "abandoned": row["abandoned"] or 0,
                    "builds": row["builds"] or 0,
                    "win_rate": _rate(row["won"] or 0, row["lost"] or 0),
                }
            )
        # Most decided games first, then by rate — a 3-1 outranks a lone 1-0.
        entries.sort(
            key=lambda e: (e["won"] + e["lost"], e["win_rate"] or 0), reverse=True
        )
        by_dimension[key] = {"label": label, "entries": entries}

    victories = [
        {"victory_type": row["victory_type"], "count": row["n"]}
        for row in conn.execute(
            """
            SELECT victory_type, COUNT(*) AS n FROM saved_builds
            WHERE outcome = 'won' AND victory_type != ''
            GROUP BY victory_type ORDER BY n DESC
            """
        ).fetchall()
    ]

    turns = conn.execute(
        """
        SELECT AVG(end_turn) AS mean, MIN(end_turn) AS fastest
        FROM saved_builds WHERE outcome = 'won' AND end_turn IS NOT NULL
        """
    ).fetchone()

    return {
        "overall": overall,
        "by_dimension": by_dimension,
        "victories": victories,
        "mean_winning_turn": round(turns["mean"]) if turns["mean"] is not None else None,
        "fastest_win_turn": turns["fastest"],
    }


# ------------------------------------------------------------------------- ratings

VERDICTS = ("a", "b", "tie")


def insert_rating_pair(
    *, experiment: str, brief_id: str, brief: dict, label_a: str, label_b: str,
    plan_a: str, plan_b: str, left_is_a: bool,
) -> int:
    conn = connect()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO rating_pairs (created_at, experiment, brief_id, brief_json,
                                      label_a, label_b, plan_a, plan_b, left_is_a)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"), experiment,
                brief_id, json.dumps(brief, ensure_ascii=False), label_a, label_b,
                plan_a, plan_b, int(bool(left_is_a)),
            ),
        )
    return cursor.lastrowid  # type: ignore[return-value]


def _blind(row: sqlite3.Row) -> dict[str, Any]:
    """A pair as the rater sees it: sides, not settings."""
    left, right = (row["plan_a"], row["plan_b"]) if row["left_is_a"] else (row["plan_b"], row["plan_a"])
    return {
        "id": row["id"],
        "experiment": row["experiment"],
        "brief_id": row["brief_id"],
        "brief": json.loads(row["brief_json"] or "{}"),
        "left": left,
        "right": right,
    }


def next_unrated_pair(experiment: str = "") -> dict[str, Any] | None:
    """The oldest pair still waiting for a verdict — blind, with no labels."""
    sql = "SELECT * FROM rating_pairs WHERE verdict = ''"
    args: list[Any] = []
    if experiment:
        sql += " AND experiment = ?"
        args.append(experiment)
    row = connect().execute(sql + " ORDER BY id LIMIT 1", args).fetchone()
    return _blind(row) if row else None


def rate_pair(pair_id: int, side: str, note: str = "") -> dict[str, Any] | None:
    """Record a verdict given by side ('left' | 'right' | 'tie'), then reveal the settings."""
    conn = connect()
    row = conn.execute("SELECT * FROM rating_pairs WHERE id = ?", (pair_id,)).fetchone()
    if row is None:
        return None
    left, right = ("a", "b") if row["left_is_a"] else ("b", "a")
    verdict = {"left": left, "right": right, "tie": "tie"}[side]
    with conn:
        conn.execute(
            "UPDATE rating_pairs SET verdict = ?, note = ?, rated_at = ? WHERE id = ?",
            (verdict, note or "", datetime.now(timezone.utc).isoformat(timespec="seconds"), pair_id),
        )
    return {
        "id": pair_id,
        "verdict": verdict,
        "left_label": row["label_a"] if row["left_is_a"] else row["label_b"],
        "right_label": row["label_b"] if row["left_is_a"] else row["label_a"],
        "winner_label": {"a": row["label_a"], "b": row["label_b"], "tie": None}[verdict],
    }


def _sign_test(wins: int, losses: int) -> float | None:
    """Two-sided exact sign test: how likely a split this lopsided is by chance.
    Ties don't count either way. None with nothing decided."""
    n = wins + losses
    if n == 0:
        return None
    from math import comb

    k = min(wins, losses)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def rating_summary() -> list[dict[str, Any]]:
    """Per experiment: how each setting fared, and whether it's more than noise."""
    rows = connect().execute(
        """
        SELECT experiment, label_a, label_b,
               COUNT(*) AS pairs,
               SUM(verdict = 'a') AS a_wins, SUM(verdict = 'b') AS b_wins,
               SUM(verdict = 'tie') AS ties, SUM(verdict = '') AS unrated,
               MIN(created_at) AS created_at
        FROM rating_pairs GROUP BY experiment, label_a, label_b ORDER BY MIN(id)
        """
    ).fetchall()
    out = []
    for r in rows:
        a, b = r["a_wins"] or 0, r["b_wins"] or 0
        out.append({
            "experiment": r["experiment"], "label_a": r["label_a"], "label_b": r["label_b"],
            "pairs": r["pairs"], "a_wins": a, "b_wins": b, "ties": r["ties"] or 0,
            "unrated": r["unrated"] or 0, "p_value": _sign_test(a, b),
        })
    return out
