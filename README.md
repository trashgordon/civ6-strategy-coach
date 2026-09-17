# Civ VI Strategy Coach

A local-first Civilization VI build coach. Set the table the way you actually play,
tell the coach what you're after, and get a complete build plan back — civ and leader,
tech path, civic path, city layout, government, dedications, and a Playbook you can
glance at mid-game. Every plan is saved to a SQLite file on your own machine, browsable
in an archive, and comparable side-by-side against past builds.

You run it yourself, with your own LLM API key. No hosted instance, no accounts.

> **Unofficial fan tool — not affiliated with, endorsed by, or connected to Firaxis
> Games or 2K.** Civilization VI and all related marks belong to their owners.

## Screenshots

| New briefing | Archive | Compare |
| --- | --- | --- |
| ![The briefing table](docs/screenshots/new-briefing.png) | ![The archive](docs/screenshots/archive.png) | ![Compare two builds](docs/screenshots/compare.png) |

## Setup

You need **Python 3.10+** and **Node 18+** (Node is only used to build the frontend once).

```bash
git clone https://github.com/trashgordon/civ6-strategy-coach.git
cd civ6-strategy-coach
cp .env.example .env        # then put your API key in it
```

Install the Python dependencies with whatever you like — [uv](https://docs.astral.sh/uv/)
is quickest:

```bash
uv venv && uv pip install -e .
```

<details>
<summary>…or plain pip / venv</summary>

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
```
</details>

Then start it:

```bash
python -m backend.run
```

That builds the frontend the first time (running `npm install && npm run build` for you),
starts the server on <http://localhost:8000>, and opens your browser. Later starts skip
the build and come up immediately; pass `--rebuild` after you pull frontend changes.

## Bring your own key

Model selection goes through [LiteLLM](https://docs.litellm.ai/), so any provider it
supports works. Set `MODEL` in your `.env` plus whichever API key matches:

```ini
# Anthropic
MODEL=anthropic/claude-sonnet-5
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
MODEL=openai/gpt-5
OPENAI_API_KEY=sk-...

# Google
MODEL=gemini/gemini-2.5-pro
GEMINI_API_KEY=...

# Fully local, no key needed (ollama serve must be running)
MODEL=ollama/llama3.1
```

> **A caveat, plainly stated:** the system prompt was tuned against Claude's
> instruction-following. Other providers should work — the call is provider-agnostic —
> but they haven't been tightly verified, especially the 8-section structure and the word
> limit. Contributions testing against other models are very welcome.

## Configuration

All of it optional except the model and its key.

| Variable | Default | What it does |
| --- | --- | --- |
| `MODEL` | `anthropic/claude-sonnet-5` | LiteLLM model string |
| *provider key* | — | e.g. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` |
| `REASONING_EFFORT` | `low` | Reasoning depth on models that reason (see below) |
| `PROMPT_CACHE` | `1` | Cache the game-facts prompt prefix (see below) |
| `CIV6_PATH` | auto-detected | Your Civ VI install, for game-data grounding |
| `FACTS_PATH` | `./data/facts` | Where extracted game names are cached |
| `DB_PATH` | `./data/strategies.db` | Where your saved builds live |
| `APP_PASSWORD` | unset | Set it to turn on a password gate (see below) |
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `8000` | Port |

### Grounding in your own game install (optional)

The coach recalls Civ VI from the model's training data, which means it can invent a
confident, plausible, non-existent name — a real plan here recommended the Golden Age
dedication "Exodus of the Evenkind", which isn't a thing.

If you own the game, you can ground it in the real thing:

```bash
python -m backend.extract_gamedata
```

That reads Firaxis's own gameplay XML and localization out of your install and caches
~2,200 canonical names (techs, civics, wonders, districts, policy cards, beliefs,
governors, governments, dedications and more) into `data/facts/`. It's auto-detected on
macOS, Windows and Linux Steam installs; set `CIV6_PATH` if not found.

Two things then happen:

- **Prevention** — the real name lists go into the prompt, so the coach picks from a
  closed set rather than recalling. Costs roughly 4,900 extra input tokens per plan
  (about +$0.012 on Claude Sonnet 5).
- **Detection** — every name the coach puts in bold is checked against the data
  afterwards, and anything unrecognised is flagged above the plan with a ⚠ marker. Free.

#### Prompt caching

The facts block is byte-identical on every call, so it's sent as a cached prefix — the
volatile part (your configuration) sits after the breakpoint and never invalidates it.
Measured on Claude Sonnet 5 with a 5,819-token facts block:

| | cost |
| --- | --- |
| First plan (writes the cache) | $0.0299 |
| Next plan within the window | **$0.0148** |

Cache reads are a tenth the price of fresh input, writes are 1.25×. So the honest
trade: **two plans inside the provider's cache window (~5 minutes) and you're well
ahead; a single isolated plan costs about $0.003 more** than not caching. Generating a
few builds in one sitting is exactly the winning case. Set `PROMPT_CACHE=0` to turn it
off. The header tooltip reports how many tokens have been served from cache.

**The extracted data is never committed.** Those names are Firaxis/2K's copyrighted
content, so this repo ships the extractor, not the output — `data/` is gitignored, and
everyone runs it against the copy of the game they own. That also means the names match
whichever DLC and patch *you* have.

Skip all of this and the app works exactly as before: no grounding, no flags, no extra
tokens. Nothing here is required.

### Reasoning models

Current reasoning models (Claude Sonnet 5 and Opus 5, OpenAI o-series, Gemini thinking
models) spend output tokens on internal reasoning *before* writing any of the answer.
Left unbounded, reasoning eats the entire token budget and you get an empty plan.

`REASONING_EFFORT` defaults to `low`, which is right for this app — the coach's brief is
deliberately short, not a proof. Measured on Claude Sonnet 5: a full 8-section plan costs
about 1,900 output tokens and lands at ~$0.02. Raise it to `medium` or `high` if you want
more deliberation and are happy to pay for it. Models that don't reason ignore it.

If a plan ever comes back empty, the error names the cause and the knob to turn rather
than just shrugging.

### Your data

Saved builds go in one SQLite file, `./data/strategies.db` by default. `data/` and `.env`
are both gitignored, so a fork can't accidentally publish your API key or your builds.
Back it up by copying that one file.

Schema changes are applied at startup from `PRAGMA user_version`, so `git pull`-ing an
update keeps your existing builds — no migration commands to run.

### Token usage and cost

Every model call is logged to an `api_calls` table with its token counts and estimated
dollar cost — build generations and compare calls alike. You'll see:

- the running total in the header, e.g. `$0.0512 over 3 calls`
- per-call tokens and cost next to each plan in the Archive, and under the compare writeup
- the full breakdown at `GET /api/usage` (lifetime totals, split by call kind, plus the
  50 most recent calls)

Costs come from [LiteLLM's pricing map](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json),
which covers a few thousand models, so the figure is an **estimate from list prices** —
it won't know about your discounts, and it can't see cache hits or batch pricing. A model
LiteLLM has no price for is still logged, with cost recorded as unknown rather than zero;
the running total then shows as `≥ $x` so it doesn't quietly under-report. Local models
(Ollama and friends) correctly come out as free.

Cost accounting never fails a request — if the price lookup breaks, you still get your
plan and the call is logged without a cost.

To total it up yourself:

```bash
sqlite3 data/strategies.db "SELECT kind, COUNT(*), ROUND(SUM(cost_usd), 4) FROM api_calls GROUP BY kind;"
```

### Password gate

There's no login by default, which is the right thing when it's just you on localhost.
If you expose the instance past localhost, set `APP_PASSWORD` and every request needs a
session cookie you get by entering that password. It's a lock on your own front door,
not a multi-user auth system — don't treat it as one, and put it behind HTTPS if it's
reachable from the internet.

## How it works

```
frontend/  React + Vite, built to static files
backend/   FastAPI — serves the API and those static files on one port
  prompts.py     both system prompts, verbatim from the brief
  llm.py         the single LiteLLM call
  db.py          SQLite + PRAGMA user_version migrations (saved_builds, api_calls)
```

The three tabs map to three endpoints: `POST /api/generate` (generate + auto-save),
`GET /api/builds` (archive, with search and filters), and `POST /api/compare` (the
side-by-side table plus a compare-and-contrast writeup from a second prompt).
`GET /api/usage` reports what all of it has cost, and `PATCH /api/builds/{id}` renames a
build or edits its campaign journal.

Smaller things worth knowing: **🎲 Surprise me** rolls a civ and all three style
dropdowns (never "No preference" — a randomiser that shrugs isn't a surprise),
**Compare with…** in the archive jumps to the Compare tab with that build already
ticked, and every saved build has a **campaign journal** for notes as the game actually
plays out.

## Development

```bash
python -m backend.run --reload     # API with auto-reload
cd frontend && npm run dev         # Vite dev server on :5173, proxying /api to :8000
pytest                             # backend tests (no API key needed — the LLM is stubbed)
```

## Contributing

Issues and PRs welcome. The feature backlog in `civ6-app-brief.md` is priority-ordered
if you're looking for somewhere to start — outcome tracking (win/loss, victory type,
turn count, and a stats view) is the next thing worth building, and it's what turns the
archive from a record into a feedback loop.

One gap worth naming: there are no JavaScript tests. The backend has 95; the markdown
renderer is verified by hand in a browser.

If you change how the coach talks, change the prompts in `civ6-app-brief.md` and
`backend/prompts.py` together — they're meant to stay identical.

## License

MIT — see [LICENSE](LICENSE).
