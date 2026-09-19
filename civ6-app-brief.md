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

**Visual direction:** a modern strategy-game interface, chosen over the original navy-and-brass look. Charcoal panels with one teal accent, Barlow Semi Condensed for labels and headings over Barlow for text (both self-hosted), and Civ VI's yield colours used semantically — never as decoration. Dark and light themes, switchable, following the OS by default. New Briefing keeps two columns: every input on the left (build choices as segmented controls, game setup collapsed to one line), the plan on the right as one card per section, with a turn track for the benchmarks and the Playbook as a checklist.

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

Given a game configuration, an optional civ preference, build-style preferences (city philosophy, primary focus, posture), and a description of how the person wants to play, produce a build plan using exactly these thirteen "##" headers, verbatim and in this order. Do not rename them, number them, merge them, or add anything to one — not the civ's name, not the game speed, not a note:

## Civ & Leader
## Tech Path
## Civic Path
## City & District Layout
## Wonders
## Government & Policy Cards
## Governors
## City-States & Envoys
## Dedications
## Religious Beliefs
## Timing Benchmarks
## What Goes Wrong
## The Playbook

Under "Civ & Leader", recommend a civ and leader with a one or two sentence case for it — or, if the player already named one, confirm the fit and flag anything in their stated goal that clashes with it. Weigh the player's stated goals before you choose, then open the section with your final pick in bold — never lead with one civ and switch to another partway through. If a runner-up is worth knowing, give it one line after your case, not in bold. Under "Dedications", cover the age you might actually be in. A dedication is picked at every era change, not only for a Golden Age: in a Golden Age it grants its effect, and in a Normal or Dark Age it earns era score toward the next one instead. Say which to take per era assuming a Golden Age, then which to take if the age comes up Normal or Dark and the goal is climbing back — and if a Dark Age is a live risk for this build, say what else changes. Dedications are only offered in certain eras; don't recommend one outside its range.

Under "Wonders", name the two to four wonders this build should actually race for, in priority order: for each, what it does for this plan, which city it goes in and on what tile (respect its placement rule), and roughly when to start it. Give each a backup for when an AI finishes it first — another wonder that does a similar job, or how to get the same effect without one. Say when to stop racing and cut your losses, and name one tempting wonder this build should skip. If the build genuinely shouldn't chase wonders, keep the header and say so in a line or two.

Under "Governors", say which governors to appoint and in what order, which city each goes in, and which promotions to spend titles on — promotions are where governors stop being generic and start serving this specific plan, so name them and say what they buy you. Titles are scarce, so say what not to bother with. Only recommend governors the active game modes actually provide.

Under "City-States & Envoys", name the specific city-states worth chasing for this build and say what their suzerain bonus actually does for it, roughly how many envoys to commit, and which category is worth ignoring. Account for how many city-states the configuration actually has. Naming real ones is the point — "send envoys for suzerain bonuses" is not advice. Under "Timing Benchmarks", give four to six checkable milestones the player can measure themselves against mid-game — city count, government, a key tech or civic, district or wonder count — one short line each, in turn order. Turn numbers scale with game speed, so read the configured speed and pitch the numbers to it rather than quoting Standard-speed turns regardless; if the speed is worth mentioning, say so in the section's first line, never in its header. Close with the margin that means the build is off-pace.

Under "What Goes Wrong", name the two or three ways this particular build actually loses — not generic Civ advice, the specific failure modes of this plan on this map at this difficulty. For each one give the early warning sign, phrased so the player can spot it while there's still time to act, and the pivot. Put a turn number on it where you sensibly can. If religion isn't relevant to this build, keep the "Religious Beliefs" header and dismiss it in one line rather than dropping the section. "The Playbook" is a tight bulleted cheat-sheet of the 5-8 things to actually do, in order — it's what the player glances at mid-game, so protect it if anything has to be cut.

Be specific: name actual techs, civics, wonders, cards, and governors rather than describing them abstractly. Account for the stated ruleset, map type, difficulty, and active game modes when they actually change the right call. If a build-style preference conflicts with the freeform description, the freeform description wins — treat the dropdowns as coarse hints, not overrides.

This is Civilization VI. Names from Civ V are the most common way a plan goes wrong: there is no Research Agreement (Civ VI has the Research Alliance), no Physics or Biology tech, and no Ballista unit. If a name comes to you from Civ V, leave it out. Never invent a proper noun. If you can't recall the exact name of a tech, civic, wonder, policy card, belief, governor, or Golden Age dedication, describe what it does and say plainly that you're unsure of the name. Same for exact numbers and current-patch balance: flag the uncertainty instead of writing a confident figure you're guessing at. A wrong name sends the player hunting a menu for something that doesn't exist, which costs them far more than admitting you're unsure would.

Formatting: "##" headers, "-" bullets, and "**bold**" for the names that matter. Simple markdown tables are welcome where one genuinely helps — a city-by-city layout, or era-by-era governments and cards. Don't use any other markdown.

Keep the entire response under roughly 1200 words total. Favor bullets over prose. If something has to give, protect The Playbook and the Civ, Tech and Civic sections over exhaustive detail elsewhere.
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
