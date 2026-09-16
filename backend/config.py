"""Environment-driven settings. Everything is optional except the model + its key."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the repo root if present. Real environment variables win.
REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env", override=False)

DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"


def model() -> str:
    return os.getenv("MODEL", DEFAULT_MODEL)


def db_path() -> Path:
    raw = os.getenv("DB_PATH", "./data/strategies.db")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def facts_path() -> Path:
    """Where extracted game data lives.

    Deliberately not derived from DB_PATH: this is a cache built from the player's game
    install, not their data, and it must sit under the gitignored `data/` directory so
    Firaxis's content is never committed. FACTS_PATH overrides it.
    """
    raw = os.getenv("FACTS_PATH", "").strip()
    if raw:
        path = Path(raw).expanduser()
        return path if path.is_absolute() else REPO_ROOT / path
    return REPO_ROOT / "data" / "facts"


def app_password() -> str | None:
    """The password gate only exists if this is set to something non-empty."""
    value = os.getenv("APP_PASSWORD", "").strip()
    return value or None


def host() -> str:
    return os.getenv("HOST", "127.0.0.1")


def port() -> int:
    return int(os.getenv("PORT", "8000"))


def frontend_dist() -> Path:
    return REPO_ROOT / "frontend" / "dist"
