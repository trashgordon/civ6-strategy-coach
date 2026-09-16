"""FastAPI app: the API plus the built frontend, on one port."""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import auth, config, db, facts, llm, prompts, summarize, titles

log = logging.getLogger("civ6")

# The prompts cap the prose at ~700 and ~400 words (roughly 1000 and 550 tokens), but a
# reasoning model spends tokens thinking before it writes any of that. Measured on Claude
# Sonnet 5 at REASONING_EFFORT=low: a full plan lands around 1,900 output tokens. These
# caps leave room for that without going so high that a non-streaming request risks an
# HTTP timeout.
MAX_PLAN_TOKENS = 4000
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


class TitleUpdate(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title cannot be empty")
        return value[:200]


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
    user_prompt = prompts.build_user_prompt(
        config=payload.config,
        civ=payload.civ,
        city_philosophy=payload.city_philosophy,
        primary_focus=payload.primary_focus,
        posture=payload.posture,
        playstyle_text=payload.playstyle_text,
    )

    try:
        result = await llm.complete(
            prompts.build_system_prompt(facts.prompt_block()),
            user_prompt,
            max_tokens=MAX_PLAN_TOKENS,
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
    build["usage"] = db.usage_for_build(build["id"])
    # Names the coach asserted that aren't in the installed game data. Empty when no
    # facts are installed — we don't flag what we can't check.
    build["unverified_names"] = facts.unverified_names(result.text)
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
    build["usage"] = db.usage_for_build(build_id)
    build["unverified_names"] = facts.unverified_names(build["generated_plan"])
    return build


@app.patch("/api/builds/{build_id}", dependencies=[Depends(require_auth)])
def rename_build(build_id: int, payload: TitleUpdate) -> dict[str, Any]:
    build = db.update_title(build_id, payload.title)
    if build is None:
        raise HTTPException(status_code=404, detail="No build with that id")
    return build


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
