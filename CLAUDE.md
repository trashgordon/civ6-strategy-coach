# Civ VI Strategy Coach

A local-first, open-source web app: a Civilization VI build coach. Configure a game setup, optionally pick a civ and three style filters, describe how you want to play, and get an AI-generated build plan — saved locally, browsable, and comparable against past builds.

**Read `civ6-app-brief.md` first**, before writing any code. It has the full feature spec, data model, both system prompts (generation + compare), and the priority-ordered feature backlog. This file stays short on purpose — the brief is the source of truth.

## Stack
- Backend: FastAPI (Python), serving both the API and the built frontend as static files
- LLM calls: LiteLLM, not a provider-specific client — see "LLM: provider-agnostic" in the brief
- Database: SQLite, one file, path from `DB_PATH` env var. Two tables: `saved_builds`
  (the archive) and `api_calls` (token counts and dollar cost per model call, including
  compare calls, which aren't tied to a saved build)
- Frontend: React, built to static files FastAPI serves — reference `civ6-strategy-coach.jsx` for the original field lists and prompt-construction logic, but that file calls the Anthropic API directly from the client; port that logic to call our own backend endpoint instead

## Conventions
- Env vars: `MODEL`, the matching provider API key, `DB_PATH` (optional, defaults to `./data/strategies.db`), `APP_PASSWORD` (optional — only enforce login if this is set)
- `data/` and `.env` are gitignored from the first commit, always
- Schema changes: bump `PRAGMA user_version` and run the needed `ALTER TABLE` at startup — no migration framework
- Build the MVP first (see the brief's feature backlog) before touching anything in the backlog list
- Backlog done so far: outcome tracking (#1), campaign journal (#3), surprise me (#8)

## Game-data grounding
`backend/extract_gamedata.py` pulls canonical names from the user's own Civ VI install
into `data/facts/` (gitignored — it's Firaxis's copyrighted content, so the repo ships
the extractor, never the data). `backend/facts.py` feeds those names into the prompt and
checks generated plans against them. `backend/ruleset.py` replays each ruleset's XML in
the game's load order to build its tech/civic tree; `backend/tree.py` puts that tree in
the prompt and checks the plan's paths against it. Every part of this must degrade to a
silent no-op when `data/facts/` is absent.

## Pipeline
Plans are made in stages by default (`backend/staged.py`): a strategist decides the plan as
JSON, it's checked exactly against the game data and repaired, then a writer turns it into
prose. The stage instructions live in `prompts.py` and verbatim in the brief, like the
system prompts. `PIPELINE=single` is the one-call path.

## Evals
Measure prompt and grounding changes with `python -m evals.run` (costs ~$0.30; say so
before running) rather than by reading one or two plans. Scoring changes don't need a
new run — `--rescore` re-applies them to the last run's saved plans. New mistakes the
coach makes go into `KNOWN_WRONG` in `evals/scoring.py`.

## Voice
Both system prompts (build generation and compare/contrast) live verbatim in the brief — reuse them as-is rather than rewriting the coach's voice from scratch.
