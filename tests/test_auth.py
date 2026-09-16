"""The password gate: absent by default, enforced when APP_PASSWORD is set."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def gated_client(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "hammurabi")
    from backend.main import app

    with TestClient(app) as client:
        yield client


def test_gate_is_invisible_without_the_env_var(client):
    assert client.get("/api/meta").json()["auth_required"] is False
    # And the API answers without any cookie.
    assert client.get("/api/builds").status_code == 200


def test_gated_api_rejects_anonymous_requests(gated_client):
    meta = gated_client.get("/api/meta").json()
    assert meta["auth_required"] is True
    assert meta["authenticated"] is False

    assert gated_client.get("/api/builds").status_code == 401
    assert gated_client.post("/api/generate", json={"config": {}}).status_code == 401


def test_login_with_the_right_password_opens_the_api(gated_client):
    assert gated_client.post("/api/login", json={"password": "sargon"}).status_code == 401

    assert gated_client.post("/api/login", json={"password": "hammurabi"}).status_code == 200
    assert gated_client.get("/api/meta").json()["authenticated"] is True
    assert gated_client.get("/api/builds").status_code == 200

    gated_client.post("/api/logout")
    assert gated_client.get("/api/builds").status_code == 401


def test_session_cookie_is_not_the_password(gated_client):
    gated_client.post("/api/login", json={"password": "hammurabi"})
    cookie = gated_client.cookies.get("civ6_coach_session")
    assert cookie and "hammurabi" not in cookie


def test_a_forged_cookie_does_not_work(gated_client):
    gated_client.cookies.set("civ6_coach_session", "let-me-in")
    assert gated_client.get("/api/builds").status_code == 401
