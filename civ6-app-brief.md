# Build Brief: Civilization VI Strategy Coach App

## Goal
An open-source, local-first web app. Anyone who clones the repo runs it on their own machine with their own LLM API key. Browser-based — one command starts a local server, opens in the browser, no install beyond that. No shared hosting, no accounts beyond an optional local password gate.

## Reference files (in this folder)
- `civ6-strategy-coach-persona.md` — the coach's voice, structure, and default game settings (Gathering Storm, Prince, Pangaea, etc.)
- `civ6-strategy-coach.jsx` — a working prototype with the full config form (every field/option list), the civ list, and prompt-construction logic. Reuse its field lists and `buildUserPrompt` logic directly. Note: it calls the Anthropic API straight from the client, which worked only inside Claude's artifact sandbox — in the real app, that call moves server-side through FastAPI + LiteLLM (see below).

## Product shape
Three-tab navigation: **New briefing** / **Archive** / **Compare**.

- **New briefing** — the config form (ruleset, difficulty, game speed, map type/size, city-states, disaster intensity, resources, world age, start position, temperature, rainfall, sea level, the 9 game-mode checkboxes), civ dropdown (optional), and three build-style dropdowns above the freeform text box:
  - City philosophy: `Tall` / `Wide` / `No preference`
  - Primary focus: `Culture` / `Science` / `Domination` / `Religion` / `Diplomacy` / `No preference`
  - Posture: `Aggressive / militaristic` / `Introverted / peaceful` / `No preference`

  Below that, the freeform "how do you want to play" box, then Generate. Every generated build auto-saves.
- **Archive** — browse/search/filter saved builds, newest first.
- **Compare** — multi-select 2+ saved builds → a structured side-by-side table (civ, focus, posture, city philosophy, key techs/wonders) plus an AI-generated compare-and-contrast writeup (separate prompt, below).

**Visual direction:** dark ink-navy panels, brass/gold accents, serif headers (Georgia/Iowan-style stack) against a clean sans-serif UI font, hairline dividers — a "campaign briefing table" feel rather than a generic SaaS dashboard. The nav tabs sit at the top; New Briefing keeps the two-column layout (config left, dossier output right) from the original prototype.

## LLM: provider-agnostic
Use **LiteLLM** (Python) rather than a hand-rolled Anthropic-only client, so the generation call is one function regardless of provider.
- A `MODEL` env var selects the model (e.g. `anthropic/claude-sonnet-4-6`, `openai/gpt-5`, `gemini/gemini-2.5-pro`, or a local Ollama model), plus whichever API key env var matches the chosen provider.
- README caveat to include, plainly stated: the system prompt was tuned against Claude's instruction-following. Other providers should work but haven't been tightly verified — contributions testing against other models are welcome.

## Data & auth: local-first, per install
- SQLite file per install. Path configurable via `DB_PATH`, defaulting to `./data/strategies.db`.
- `data/` and `.env` are gitignored from the very first commit — never let a fork accidentally commit someone's saved builds or API key.
- No forced login. A password gate only activates if `APP_PASSWORD` is set — invisible by default for someone just running it locally for themselves, available for anyone who exposes their instance beyond localhost.
- Lightweight schema versioning: a `PRAGMA user_version` check at startup runs any needed `ALTER TABLE` statements and bumps the version. No migration framework needed for one table — but this matters since people will `git pull` updates and expect their existing saved builds to keep working.

## Data model
```
saved_builds
  id                integer primary key
  created_at        timestamp
  title             text            -- editable, auto-suggested on save
  ruleset           text
  difficulty        text
  map_type          text
  config_json       text            -- full config form state
  civ               text            -- may be empty ("no preference")
  city_philosophy   text            -- tall / wide / no preference
  primary_focus     text            -- culture / science / domination / religion / diplomacy / no preference
  posture           text            -- aggressive / introverted / no preference
  playstyle_text    text            -- the freeform box
  generated_plan    text            -- the full markdown build plan
```

## System prompt — build generation (reuse as-is)
```
You are a former competitive Civilization VI player who went pro on the tournament circuit before becoming a coach. You know the tech tree, civic tree, civs, leaders, governors, wonders, and policy cards cold, and you're just as sharp on general strategy game theory (tempo, snowballing, opportunity cost, opponent-reading) as you are on Civ 6 specifics.

Talk like a coach, not a wiki: direct, opinionated, no padding. State the recommendation first, then justify briefly.

Given a game configuration, an optional civ preference, build-style preferences (city philosophy, primary focus, posture), and a description of how the person wants to play, produce a build plan using exactly these eleven "##" headers, verbatim and in this order. Do not rename them, number them, merge them, or append the civ's name to one:

## Civ & Leader
## Tech Path
## Civic Path
## City & District Layout
## Government & Policy Cards
## City-States & Envoys
## Golden Age Dedications
## Religious Beliefs
## Timing Benchmarks
## What Goes Wrong
## The Playbook

Under "Civ & Leader", recommend a civ and leader with a one or two sentence case for it — or, if the player already named one, confirm the fit and flag anything in their stated goal that clashes with it. Under "City-States & Envoys", name the specific city-states worth chasing for this build and say what their suzerain bonus actually does for it, roughly how many envoys to commit, and which category is worth ignoring. Account for how many city-states the configuration actually has. Naming real ones is the point — "send envoys for suzerain bonuses" is not advice. Under "Timing Benchmarks", give four to six checkable milestones the player can measure themselves against mid-game — city count, government, a key tech or civic, district or wonder count — one short line each, in turn order. Turn numbers scale with game speed, so read the configured speed and pitch the numbers to it rather than quoting Standard-speed turns regardless. Close with the margin that means the build is off-pace.

Under "What Goes Wrong", name the two or three ways this particular build actually loses — not generic Civ advice, the specific failure modes of this plan on this map at this difficulty. For each one give the early warning sign, phrased so the player can spot it while there's still time to act, and the pivot. Put a turn number on it where you sensibly can. If religion isn't relevant to this build, keep the "Religious Beliefs" header and dismiss it in one line rather than dropping the section. "The Playbook" is a tight bulleted cheat-sheet of the 5-8 things to actually do, in order — it's what the player glances at mid-game, so protect it if anything has to be cut.

Be specific: name actual techs, civics, wonders, cards, and governors rather than describing them abstractly. Account for the stated ruleset, map type, difficulty, and active game modes when they actually change the right call. If a build-style preference conflicts with the freeform description, the freeform description wins — treat the dropdowns as coarse hints, not overrides.

Never invent a proper noun. If you can't recall the exact name of a tech, civic, wonder, policy card, belief, governor, or Golden Age dedication, describe what it does and say plainly that you're unsure of the name. Same for exact numbers and current-patch balance: flag the uncertainty instead of writing a confident figure you're guessing at. A wrong name sends the player hunting a menu for something that doesn't exist, which costs them far more than admitting you're unsure would.

Formatting: "##" headers, "-" bullets, and "**bold**" for the names that matter. Simple markdown tables are welcome where one genuinely helps — a city-by-city layout, or era-by-era governments and cards. Don't use any other markdown.

Keep the entire response under roughly 1000 words total. Favor bullets over prose. If something has to give, protect The Playbook and the Civ, Tech and Civic sections over exhaustive detail elsewhere.
```

## System prompt — compare/contrast (reuse as-is)
```
You are the same Civilization VI coach. You'll be given 2 or more saved build plans. Write a compare-and-contrast briefing covering:
1. What these builds have in common (shared mechanics, overlapping strengths)
2. Where they genuinely diverge, and why that divergence matters in practice
3. A short verdict: which build fits which situation or mood best — don't just declare an overall winner, since these were built for different goals

Stay specific and opinionated, same voice as always. Keep it under 400 words.
```

## Open-source distribution checklist
- README: what it does, a couple screenshots, one-command setup, bring-your-own-key instructions (at least Anthropic, ideally showing the LiteLLM env var pattern for others too), and an explicit "unofficial fan tool — not affiliated with Firaxis or 2K" disclaimer.
- Pick a license — MIT is the standard low-friction default for something like this.
- `.gitignore` from commit one: `data/`, `.env`, `__pycache__/`, `node_modules/`, and whatever the frontend build output directory is.
- No shared/hosted instance in v1 — clone-and-run only. A rate-limited public demo is a possible future add-on, not part of this build.

## Feature backlog (build the MVP first — this is priority-ordered, not required)
MVP = config form + 3 style dropdowns + freeform text → generate → auto-save → archive → compare. Everything below is a deliberate follow-up, not scope creep to solve now:

1. **Outcome tracking** — log win/loss, victory type, and turn count per saved build; a stats view (win rate by civ/focus/posture). This is the one that turns the archive into a real feedback loop instead of a scrapbook — prioritize it first.
2. **Pattern-calling** — the coach notices repeated patterns across saved builds (e.g. always Culture + Tall) and can proactively suggest a deliberately different build.
3. **Campaign journal** — a free-text notes field attached to each saved build, editable as a game progresses.
4. **Screenshot check-ins** — accept an image (tech tree, city screen) mid-game and react to the actual game state, not just the original plan.
5. **Emergency tactical mode** — a short "something just happened" input that skips the 8-section format for a 3-bullet immediate response.
6. **Visual tech/civic timeline** — a diagram view of the beeline instead of a bulleted list.
7. **Compare debate mode** — the compare view has the coach argue for each build against the other before landing on a verdict.
8. **Surprise me button** — randomizes civ plus all three style dropdowns.
9. **Speedrun mode** — a target turn count input that produces a more aggressive, optimized-for-speed plan.
10. **Shareable build card** — export a saved build as a single-image summary card (civ, focus, Playbook bullets).
