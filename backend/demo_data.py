"""Fill a throwaway database with plausible builds and results, to see Stats working.

    python -m backend.demo_data                 # writes data/demo.db
    DB_PATH=./data/demo.db PORT=8001 python -m backend.run

The builds have no generated plans — each carries a short note saying it's demo data —
because the point is the Stats view, and generating thirty real plans would cost money
for nothing. The results are invented but not random noise: a few patterns are baked in
(tall science tends to win, naval domination on Archipelago tends not to, harder
difficulties lose more) so the breakdown tables have something to show.

Refuses to write to the database the app is configured to use, so it can't overwrite
your real archive.
"""

import argparse
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, db, titles

DEMO_PLAN = (
    "## Demo build\n"
    "This build was created by `python -m backend.demo_data` to populate the Stats "
    "view. No plan was generated for it."
)

# Which civs tend to get picked for which focus. The rest of the time it's any civ.
AFFINITY = {
    "Science": ["Korea", "Babylon", "Scotland", "Japan"],
    "Culture": ["Greece", "France", "Kongo", "Maori"],
    "Domination": ["Rome", "Mongolia", "Zulu", "Aztec", "Macedon"],
    "Religion": ["Russia", "Ethiopia", "Khmer", "Arabia"],
    "Diplomacy": ["England", "Canada", "Sweden", "Hungary"],
}
ALL_CIVS = sorted({c for civs in AFFINITY.values() for c in civs} | {"Egypt", "China", "Persia"})

# What a won game of each focus usually counts as, and roughly when it lands.
VICTORY_FOR = {
    "Science": "Science", "Culture": "Culture", "Domination": "Domination",
    "Religion": "Religious", "Diplomacy": "Diplomatic",
}
TURN_RANGE = {
    "Science": (225, 290), "Culture": (235, 300), "Domination": (175, 260),
    "Religious": (165, 240), "Diplomatic": (240, 310), "Score": (480, 500),
}

MAPS = ["Pangaea"] * 6 + ["Continents"] * 2 + ["Highlands", "Archipelago", "Fractal"]
DIFFICULTIES = ["Prince"] * 5 + ["King"] * 3 + ["Emperor"] * 2


def _win_chance(focus: str, philosophy: str, posture: str, map_type: str, difficulty: str) -> float:
    chance = 0.6
    if focus == "Science" and philosophy == "Tall":
        chance += 0.3
    if focus == "Domination" and map_type == "Archipelago":
        chance -= 0.45
    if focus == "Religion":
        chance -= 0.15
    if posture.startswith("Aggressive") and map_type == "Pangaea":
        chance += 0.1
    chance -= {"Prince": 0.0, "King": 0.18, "Emperor": 0.35}[difficulty]
    return max(0.05, min(0.95, chance))


def generate(path: Path, count: int, seed: int) -> dict:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    summary = {"builds": 0, "won": 0, "lost": 0, "abandoned": 0, "unrecorded": 0}

    for i in range(count):
        focus = rng.choice(list(AFFINITY))
        civ = rng.choice(AFFINITY[focus]) if rng.random() < 0.7 else rng.choice(ALL_CIVS)
        philosophy = rng.choice(["Tall", "Tall", "Wide"] if focus in ("Science", "Culture") else ["Wide", "Wide", "Tall"])
        posture = (
            "Aggressive / militaristic" if focus == "Domination"
            else rng.choice(["Introverted / peaceful", "Introverted / peaceful", "No preference"])
        )
        map_type = rng.choice(MAPS)
        difficulty = rng.choice(DIFFICULTIES)
        cfg = {
            "ruleset": "Gathering Storm", "difficulty": difficulty, "gameSpeed": "Standard",
            "mapType": map_type, "mapSize": "Standard", "cityStates": 12,
            "disasterIntensity": 2, "resources": "Abundant", "worldAge": "New",
            "startPosition": "Legendary", "temperature": "Standard", "rainfall": "Wet",
            "seaLevel": "Standard", "modes": {"monopolies": True, "sukritactOceans": True},
        }

        build = db.insert_build(
            title=titles.suggest_title(civ=civ, city_philosophy=philosophy,
                                       primary_focus=focus, posture=posture, plan=""),
            config_dict=cfg, civ=civ, city_philosophy=philosophy, primary_focus=focus,
            posture=posture, playstyle_text="", generated_plan=DEMO_PLAN,
        )

        roll = rng.random()
        if roll < 0.15:
            summary["unrecorded"] += 1
        elif roll < 0.23:
            db.update_build(build["id"], outcome="abandoned",
                            end_turn=rng.randint(60, 160))
            summary["abandoned"] += 1
        elif rng.random() < _win_chance(focus, philosophy, posture, map_type, difficulty):
            victory = "Score" if rng.random() < 0.08 else VICTORY_FOR[focus]
            low, high = TURN_RANGE[victory]
            db.update_build(build["id"], outcome="won", victory_type=victory,
                            end_turn=rng.randint(low, high))
            summary["won"] += 1
        else:
            db.update_build(build["id"], outcome="lost", end_turn=rng.randint(120, 330))
            summary["lost"] += 1

        # Spread the builds over the last few months so the archive reads naturally.
        when = now - timedelta(days=(count - i) * rng.uniform(2.0, 5.0), hours=rng.uniform(0, 12))
        db.connect().execute(
            "UPDATE saved_builds SET created_at = ? WHERE id = ?",
            (when.isoformat(timespec="seconds"), build["id"]),
        )
        db.connect().commit()
        summary["builds"] += 1

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a demo database for the Stats view.")
    parser.add_argument("--db", default=str(config.REPO_ROOT / "data" / "demo.db"),
                        help="where to write it (default data/demo.db)")
    parser.add_argument("--count", type=int, default=40, help="number of builds (default 40)")
    parser.add_argument("--seed", type=int, default=6, help="random seed, for repeatable data")
    args = parser.parse_args(argv)

    target = Path(args.db).expanduser().resolve()
    if target == config.db_path().resolve():
        print(f"Refusing to write demo data into your real database at {target}.\n"
              f"Pass a different --db, or unset DB_PATH.", file=sys.stderr)
        return 2

    # Always start from empty: this is a throwaway, and appending would skew the stats.
    for suffix in ("", "-wal", "-shm"):
        Path(f"{target}{suffix}").unlink(missing_ok=True)

    config_db_path = config.db_path
    config.db_path = lambda: target
    try:
        db.close()
        db.migrate()
        summary = generate(target, args.count, args.seed)
    finally:
        db.close()
        config.db_path = config_db_path

    print(f"  wrote {summary['builds']} demo builds to {target}")
    print(f"  {summary['won']} won · {summary['lost']} lost · "
          f"{summary['abandoned']} abandoned · {summary['unrecorded']} not recorded")
    print(f"\n  See it with:\n    DB_PATH={target} PORT=8001 python -m backend.run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
