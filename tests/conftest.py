import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SAMPLE_PLAN = """## Civ & Leader recommendation
**Korea — Seondeok**. Seowons are the fastest science engine in the game on a Pangaea
start, and Prince gives you room to skip early defense.

## Tech path
- **Writing** first, then **Currency**
- Beeline **Astrology** only if you took a Holy Site

## Civic path
- **Political Philosophy** for Oligarchy

## City & district layout
Keep cities three tiles apart so every Seowon gets its hill.

## Government & policy cards
Oligarchy, then Monarchy.

## Golden Age dedication priorities
Free Inquiry in Classical.

## The Playbook
- Settle on a hill next to two mountains
- Build a Seowon in every city
"""


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch):
    """Every test gets its own database, no password gate, and a stubbed model."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setenv("MODEL", "anthropic/claude-sonnet-4-6")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    from backend import db

    db.close()
    yield
    db.close()


@pytest.fixture
def stub_llm(monkeypatch):
    """Replace the LLM call, recording the prompts it was handed."""
    calls: list[dict] = []

    async def fake_complete(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        calls.append(
            {"system": system_prompt, "user": user_prompt, "max_tokens": max_tokens}
        )
        if "compare-and-contrast" in system_prompt:
            return "## Common ground\nBoth lean on **Seowon** adjacency."
        return SAMPLE_PLAN

    from backend import llm

    monkeypatch.setattr(llm, "complete", fake_complete)
    return calls


@pytest.fixture
def client():
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_config():
    return {
        "ruleset": "Gathering Storm",
        "difficulty": "Prince",
        "gameSpeed": "Standard",
        "mapType": "Pangaea",
        "mapSize": "Standard",
        "cityStates": 12,
        "disasterIntensity": 2,
        "resources": "Abundant",
        "worldAge": "New",
        "startPosition": "Legendary",
        "temperature": "Standard",
        "rainfall": "Wet",
        "seaLevel": "Standard",
        "modes": {"monopolies": True, "sukritactOceans": True, "apocalypse": False},
    }
