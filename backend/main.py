"""FastAPI app: the API plus the built frontend, on one port."""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import auth, config, db, facts, generation, llm, prompts, summarize, titles, tree

log = logging.getLogger("civ6")

# The compare writeup is capped at ~400 words; see generation.py for why the caps sit
# well above the prose length on a reasoning model.
MAX_COMPARE_TOKENS = 2500


@asynccontextmanager
async def lifespan(app: FastAPI):
    version = db.migrate()
    log.info("database ready at %s (schema v%s)", db.db_file(), version)
    if auth.enabled():
        log.info("APP_PASSWORD is set — the password gate is active")
    yield
    db.close()


app = FastAPI(title="Civ VI Strategy Coach", lifespan=lifespan)


# --------------------------------------------------------------------------- models


class GenerateRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    civ: str = ""
    city_philosophy: str = ""
    primary_focus: str = ""
    posture: str = ""
    playstyle_text: str = ""

    @field_validator("playstyle_text")
    @classmethod
    def cap_playstyle(cls, value: str) -> str:
        if len(value) > 4000:
            raise ValueError("playstyle_text is too long (4000 character limit)")
        return value


class BuildUpdate(BaseModel):
    """Any field may be omitted; whatever is sent is what changes."""

    title: str | None = None
    notes: str | None = None
    outcome: str | None = None
    victory_type: str | None = None
    end_turn: int | None = None

    @field_validator("outcome")
    @classmethod
    def known_outcome(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        # "" clears it back to unrecorded, which is a legitimate edit.
        if value and value not in db.OUTCOMES:
            raise ValueError(f"outcome must be one of {', '.join(db.OUTCOMES)}, or empty")
        return value

    @field_validator("victory_type")
    @classmethod
    def known_victory(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return ""
        match = {v.lower(): v for v in db.VICTORY_TYPES}.get(value.lower())
        if match is None:
            raise ValueError(
                f"victory_type must be one of {', '.join(db.VICTORY_TYPES)}, or empty"
            )
        return match

    @field_validator("end_turn")
    @classmethod
    def sane_turn(cls, value: int | None) -> int | None:
        if value is None:
            return None
        # 0 clears it; a real game can't end before turn 1 or run past a few thousand.
        if value and not (1 <= value <= 5000):
            raise ValueError("end_turn must be between 1 and 5000, or 0 to clear it")
        return value

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("title cannot be empty")
        return value[:200]

    @field_validator("notes")
    @classmethod
    def cap_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) > 20000:
            raise ValueError("notes are too long (20000 character limit)")
        return value


class CompareRequest(BaseModel):
    build_ids: list[int]

    @field_validator("build_ids")
    @classmethod
    def at_least_two(cls, value: list[int]) -> list[int]:
        # Dedupe while keeping the order the user picked them in.
        unique = list(dict.fromkeys(value))
        if len(unique) < 2:
            raise ValueError("pick at least two builds to compare")
        if len(unique) > 5:
            raise ValueError("compare up to five builds at a time")
        return unique


class LoginRequest(BaseModel):
    password: str


# ----------------------------------------------------------------------------- auth


def require_auth(request: Request) -> None:
    if not auth.is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")


@app.get("/api/meta")
def meta(request: Request) -> dict[str, Any]:
    """Public: tells the frontend whether to show a login screen, and what model is set."""
    return {
        "auth_required": auth.enabled(),
        "authenticated": auth.is_authenticated(request),
        "model": config.model(),
        "missing_key": llm.missing_key_hint(),
        "facts_available": facts.available(),
        "facts_counts": facts.summary(),
    }


@app.post("/api/login")
def login(payload: LoginRequest, response: Response) -> dict[str, Any]:
    if not auth.enabled():
        return {"authenticated": True}
    if not auth.check_password(payload.password):
        raise HTTPException(status_code=401, detail="Wrong password")
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.issue_token(),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return {"authenticated": True}


@app.post("/api/logout")
def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(auth.COOKIE_NAME)
    return {"authenticated": False}


# ------------------------------------------------------------------------- briefing


@app.post("/api/generate", dependencies=[Depends(require_auth)])
async def generate(payload: GenerateRequest) -> dict[str, Any]:
    """Generate a build plan and save it. Every generated build auto-saves."""
    try:
        result = await generation.draft_plan(
            config=payload.config,
            civ=payload.civ,
            city_philosophy=payload.city_philosophy,
            primary_focus=payload.primary_focus,
            posture=payload.posture,
            playstyle_text=payload.playstyle_text,
        )
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    title = titles.suggest_title(
        civ=payload.civ,
        city_philosophy=payload.city_philosophy,
        primary_focus=payload.primary_focus,
        posture=payload.posture,
        plan=result.text,
    )

    build = db.insert_build(
        title=title,
        config_dict=payload.config,
        civ=payload.civ,
        city_philosophy=payload.city_philosophy,
        primary_focus=payload.primary_focus,
        posture=payload.posture,
        playstyle_text=payload.playstyle_text,
        generated_plan=result.text,
        truncated=result.truncated,
    )

    db.insert_api_call(
        kind=db.GENERATE,
        build_id=build["id"],
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost_usd=result.cost_usd,
        cache_write_tokens=result.cache_write_tokens,
        cache_read_tokens=result.cache_read_tokens,
    )
    return _with_checks(build)


def _with_checks(build: dict[str, Any]) -> dict[str, Any]:
    """Usage plus the grounding checks. Both checks are empty when no facts are
    installed — we don't flag what we can't check."""
    plan = build["generated_plan"]
    build["usage"] = db.usage_for_build(build["id"])
    # Names the coach asserted that aren't in the installed game data.
    build["unverified_names"] = facts.unverified_names(plan)
    # Tech/civic paths out of order, in the wrong tree, or crediting the wrong unlock.
    build["tree_issues"] = tree.path_issues(plan, build.get("ruleset"))
    return build


# -------------------------------------------------------------------------- archive


@app.get("/api/builds", dependencies=[Depends(require_auth)])
def list_builds(q: str = "", civ: str = "", primary_focus: str = "") -> dict[str, Any]:
    return {
        "builds": db.list_builds(query=q, civ=civ, primary_focus=primary_focus),
        "filters": {
            "civs": db.distinct_values("civ"),
            "focuses": db.distinct_values("primary_focus"),
        },
    }


@app.get("/api/builds/{build_id}", dependencies=[Depends(require_auth)])
def get_build(build_id: int) -> dict[str, Any]:
    build = db.get_build(build_id)
    if build is None:
        raise HTTPException(status_code=404, detail="No build with that id")
    return _with_checks(build)


@app.patch("/api/builds/{build_id}", dependencies=[Depends(require_auth)])
def update_build(build_id: int, payload: BuildUpdate) -> dict[str, Any]:
    """Rename a build and/or edit its campaign journal."""
    if db.get_build(build_id) is None:
        raise HTTPException(status_code=404, detail="No build with that id")
    build = db.update_build(
        build_id,
        title=payload.title,
        notes=payload.notes,
        outcome=payload.outcome,
        victory_type=payload.victory_type,
        end_turn=payload.end_turn or None,
        clear_end_turn=payload.end_turn == 0,
    )
    return _with_checks(build)


@app.delete("/api/builds/{build_id}", dependencies=[Depends(require_auth)])
def delete_build(build_id: int) -> dict[str, Any]:
    if not db.delete_build(build_id):
        raise HTTPException(status_code=404, detail="No build with that id")
    return {"deleted": build_id}


# ---------------------------------------------------------------------------- usage


@app.get("/api/usage", dependencies=[Depends(require_auth)])
def usage() -> dict[str, Any]:
    """Lifetime tokens and spend, plus the most recent calls."""
    totals = db.usage_totals()
    totals["recent"] = db.recent_api_calls(limit=50)
    return totals


@app.get("/api/stats", dependencies=[Depends(require_auth)])
def stats() -> dict[str, Any]:
    """Win/loss records, overall and by civ, focus, posture, map and difficulty."""
    body = db.outcome_stats()
    body["outcomes"] = list(db.OUTCOMES)
    body["victory_types"] = list(db.VICTORY_TYPES)
    return body


# -------------------------------------------------------------------------- compare


@app.post("/api/compare", dependencies=[Depends(require_auth)])
async def compare(payload: CompareRequest) -> dict[str, Any]:
    builds = db.get_builds(payload.build_ids)
    if len(builds) < 2:
        raise HTTPException(
            status_code=404, detail="Couldn't find at least two of those builds"
        )

    try:
        result = await llm.complete(
            prompts.COMPARE_SYSTEM_PROMPT,
            prompts.compare_user_prompt(builds),
            max_tokens=MAX_COMPARE_TOKENS,
        )
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    db.insert_api_call(
        kind=db.COMPARE,
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost_usd=result.cost_usd,
        cache_write_tokens=result.cache_write_tokens,
        cache_read_tokens=result.cache_read_tokens,
    )

    return {
        "rows": [summarize.compare_row(build) for build in builds],
        "writeup": result.text,
        "usage": {
            "model": result.model,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "cost_usd": result.cost_usd,
        },
    }


# ------------------------------------------------------------------- static frontend

NO_BUILD_MESSAGE = """The frontend isn't built yet.

Build it once:

    cd frontend && npm install && npm run build

Or just use the launcher, which does it for you:

    python -m backend.run
"""


def mount_frontend() -> None:
    """Serve frontend/dist if it's been built, with an SPA fallback for the tabs."""
    dist = config.frontend_dist()
    assets = dist / "assets"
    index = dist / "index.html"

    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="No such endpoint")
        candidate = (dist / full_path).resolve()
        # Only serve real files that are genuinely inside dist.
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        if index.is_file():
            return FileResponse(index)
        return PlainTextResponse(NO_BUILD_MESSAGE, status_code=503)


mount_frontend()


@app.exception_handler(ValueError)
def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
