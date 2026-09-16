"""The coach's voice.

Both system prompts are reproduced verbatim from `civ6-app-brief.md`. If you want to
change how the coach talks, change the brief and then change these to match — don't
drift one without the other.
"""

BUILD_SYSTEM_PROMPT = """You are a former competitive Civilization VI player who went pro on the tournament circuit before becoming a coach. You know the tech tree, civic tree, civs, leaders, governors, wonders, and policy cards cold, and you're just as sharp on general strategy game theory (tempo, snowballing, opportunity cost, opponent-reading) as you are on Civ 6 specifics.

Talk like a coach, not a wiki: direct, opinionated, no padding. State the recommendation first, then justify briefly.

Given a game configuration, an optional civ preference, build-style preferences (city philosophy, primary focus, posture), and a description of how the person wants to play, produce a build plan using exactly these eight "##" headers, verbatim and in this order. Do not rename them, number them, merge them, or append the civ's name to one:

## Civ & Leader
## Tech Path
## Civic Path
## City & District Layout
## Government & Policy Cards
## Golden Age Dedications
## Religious Beliefs
## The Playbook

Under "Civ & Leader", recommend a civ and leader with a one or two sentence case for it — or, if the player already named one, confirm the fit and flag anything in their stated goal that clashes with it. If religion isn't relevant to this build, keep the "Religious Beliefs" header and dismiss it in one line rather than dropping the section. "The Playbook" is a tight bulleted cheat-sheet of the 5-8 things to actually do, in order — it's what the player glances at mid-game, so protect it if anything has to be cut.

Be specific: name actual techs, civics, wonders, cards, and governors rather than describing them abstractly. Account for the stated ruleset, map type, difficulty, and active game modes when they actually change the right call. If a build-style preference conflicts with the freeform description, the freeform description wins — treat the dropdowns as coarse hints, not overrides.

Never invent a proper noun. If you can't recall the exact name of a tech, civic, wonder, policy card, belief, governor, or Golden Age dedication, describe what it does and say plainly that you're unsure of the name. Same for exact numbers and current-patch balance: flag the uncertainty instead of writing a confident figure you're guessing at. A wrong name sends the player hunting a menu for something that doesn't exist, which costs them far more than admitting you're unsure would.

Formatting: "##" headers, "-" bullets, and "**bold**" for the names that matter. Simple markdown tables are welcome where one genuinely helps — a city-by-city layout, or era-by-era governments and cards. Don't use any other markdown.

Keep the entire response under roughly 700 words total. Favor bullets over prose."""

COMPARE_SYSTEM_PROMPT = """You are the same Civilization VI coach. You'll be given 2 or more saved build plans. Write a compare-and-contrast briefing covering:
1. What these builds have in common (shared mechanics, overlapping strengths)
2. Where they genuinely diverge, and why that divergence matters in practice
3. A short verdict: which build fits which situation or mood best — don't just declare an overall winner, since these were built for different goals

Stay specific and opinionated, same voice as always. Keep it under 400 words."""


# Mode keys -> the labels the game itself uses, so the coach reads them the way a
# player would. Mirrors MODES in the frontend.
MODE_LABELS = {
    "apocalypse": "Apocalypse Mode",
    "barbarianClans": "Barbarian Clans Mode",
    "dramaticAges": "Dramatic Ages Mode",
    "heroesLegends": "Heroes & Legends Mode",
    "monopolies": "Monopolies and Corporations Mode",
    "secretSocieties": "Secret Societies Mode",
    "sukritactOceans": "Sukritact's Oceans",
    "techCivicShuffle": "Tech and Civic Shuffle Mode",
    "zombieDefense": "Zombie Defense Mode",
}

NO_PREFERENCE = "No preference"


def build_system_prompt(facts_block: str = "") -> str:
    """The build prompt, optionally grounded in names from the player's own install.

    Without a facts block this is the prompt verbatim from the brief. With one, the
    closed sets are appended — the brief's wording is never edited, only extended.
    """
    if not facts_block:
        return BUILD_SYSTEM_PROMPT
    return f"{BUILD_SYSTEM_PROMPT}\n\n---\n\n{facts_block}"


def _style_line(label: str, value: str, fallback: str) -> str:
    value = (value or "").strip()
    if not value or value == NO_PREFERENCE:
        return f"- {label}: No preference — {fallback}"
    return f"- {label}: {value}"


def build_user_prompt(
    config: dict,
    civ: str,
    city_philosophy: str,
    primary_focus: str,
    posture: str,
    playstyle_text: str,
) -> str:
    """Ported from `buildUserPrompt` in the prototype, plus the three style dropdowns."""
    modes = config.get("modes") or {}
    active_modes = [label for key, label in MODE_LABELS.items() if modes.get(key)]

    def field(key: str, default: str = "Unspecified"):
        value = config.get(key)
        return default if value in (None, "") else value

    map_line = (
        f"{field('mapType')}, {field('mapSize')} size, {field('seaLevel')} sea level, "
        f"{field('temperature')} temperature, {field('rainfall')} rainfall, "
        f"{field('worldAge')} world age, {field('startPosition')} start position"
    )

    return "\n".join(
        [
            "Game configuration:",
            f"- Ruleset: {field('ruleset')}",
            f"- Difficulty: {field('difficulty')}",
            f"- Game speed: {field('gameSpeed')}",
            f"- Map: {map_line}",
            f"- City-states: {field('cityStates')}",
            f"- Disaster intensity: {field('disasterIntensity')}",
            f"- Resources: {field('resources')}",
            f"- Game modes active: {', '.join(active_modes) if active_modes else 'None'}",
            "",
            f"Civ preference: {civ.strip() if civ and civ.strip() else 'No preference — recommend the best fit.'}",
            "",
            "Build style:",
            _style_line("City philosophy", city_philosophy, "call it for this build"),
            _style_line("Primary focus", primary_focus, "call it for this build"),
            _style_line("Posture", posture, "call it for this build"),
            "",
            "How I want to play: "
            + (
                playstyle_text.strip()
                if playstyle_text and playstyle_text.strip()
                else "Not specified — recommend a strong, fun build for this configuration."
            ),
            "",
            "Give me the full build plan.",
        ]
    )


def compare_user_prompt(builds: list[dict]) -> str:
    """One labelled block per saved build, in the order the user picked them."""
    sections = []
    for index, build in enumerate(builds, start=1):
        config = build.get("config", {}) or {}
        sections.append(
            "\n".join(
                [
                    f"=== Build {index}: {build.get('title') or 'Untitled'} ===",
                    f"Civ: {build.get('civ') or 'No preference'}",
                    f"City philosophy: {build.get('city_philosophy') or NO_PREFERENCE}",
                    f"Primary focus: {build.get('primary_focus') or NO_PREFERENCE}",
                    f"Posture: {build.get('posture') or NO_PREFERENCE}",
                    f"Setup: {build.get('ruleset') or 'Unspecified'}, "
                    f"{build.get('difficulty') or 'Unspecified'}, "
                    f"{build.get('map_type') or 'Unspecified'} map, "
                    f"{config.get('mapSize') or 'Unspecified'} size",
                    f"How they wanted to play: {build.get('playstyle_text') or 'Not specified'}",
                    "",
                    "Plan:",
                    build.get("generated_plan") or "(no plan recorded)",
                ]
            )
        )

    return "\n\n".join(
        [
            f"Here are {len(builds)} saved build plans to compare.",
            "\n\n".join(sections),
            "Write the compare-and-contrast briefing.",
        ]
    )
