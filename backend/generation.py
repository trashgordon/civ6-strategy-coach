"""Drafting a build plan: the one path both the API and the eval harness go through.

Kept separate from the endpoint so `evals/` measures exactly what the app sends — same
prompt assembly, same grounding, same token cap — rather than a copy that can drift.
"""

import os
import re
from typing import Any

from . import facts, llm, prompts

# The prompt caps the prose at ~1100 words, but a reasoning model spends tokens thinking
# before it writes any of that. Measured on Claude Sonnet 5 at REASONING_EFFORT=low: a
# ~1100-word plan lands around 2,900 output tokens. The cap leaves room for that without
# going so high that a non-streaming request risks an HTTP timeout — a 16,000-token
# attempt disconnected mid-call.
MAX_PLAN_TOKENS = 6000

# More effort means more thinking before the first word of the plan, and the thinking is
# billed against the same max_tokens. Measured on the plan prompt: at "medium", 5 of 6
# plans used all 6,000 tokens and stopped mid-section; the one that finished used 4,862.
_CAP_BY_EFFORT = {"minimal": 6000, "low": 6000, "medium": 12000, "high": 12000}


def plan_token_cap() -> int:
    """max_tokens for a plan at the configured REASONING_EFFORT; PLAN_MAX_TOKENS overrides."""
    override = os.getenv("PLAN_MAX_TOKENS", "").strip()
    if override.isdigit() and int(override) > 0:
        return int(override)
    return _CAP_BY_EFFORT.get(llm.REASONING_EFFORT, MAX_PLAN_TOKENS)


def system_prompt(ruleset: str | None = None) -> str:
    """The build prompt as actually sent, grounding (and that ruleset's tree) included."""
    return prompts.build_system_prompt(facts.prompt_block(ruleset=ruleset))


_HEADER = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)
_NUMBERING = re.compile(r"^(?:\d+[.)]\s*|#\d+\s*)")


def tidy_headers(plan: str) -> str:
    """Put decorated headers back to the exact thirteen the app renders by name.

    "## Timing Benchmarks (Standard speed)" keeps happening despite the prompt forbidding
    it (1 in 6 plans, at any reasoning effort), and the app keys section rendering on the
    exact name — that plan lost its turn track. So strip the decoration and keep what it
    said as the section's first line. Headers that aren't a known one plus decoration are
    left alone.
    """
    expected = prompts.expected_headers()
    lowered = {h.lower(): h for h in expected}

    def fix(match: re.Match) -> str:
        raw = match.group(1)
        if raw in expected:
            return match.group(0)
        text = _NUMBERING.sub("", raw).strip()
        if text.lower() in lowered:
            return f"## {lowered[text.lower()]}"
        for header in sorted(expected, key=len, reverse=True):
            if not text.lower().startswith(header.lower()):
                continue
            extra = text[len(header):].strip()
            if not extra or extra[0] not in "(:—–-[":
                continue  # "Governors & Titles" is a different header, not decoration
            extra = extra.strip(" ()[]:—–-").strip()
            note = f"\n\n{extra[0].upper()}{extra[1:]}." if extra else ""
            return f"## {header}{note.rstrip('.') + '.' if note else ''}"
        return match.group(0)

    return _HEADER.sub(fix, plan)


async def draft_plan(
    *,
    config: dict[str, Any],
    civ: str = "",
    city_philosophy: str = "",
    primary_focus: str = "",
    posture: str = "",
    playstyle_text: str = "",
) -> llm.Completion:
    """Generate one plan. Raises llm.LLMError on failure; saves nothing."""
    user_prompt = prompts.build_user_prompt(
        config=config,
        civ=civ,
        city_philosophy=city_philosophy,
        primary_focus=primary_focus,
        posture=posture,
        playstyle_text=playstyle_text,
        speed_multiplier=facts.game_speeds().get(str(config.get("gameSpeed") or "")),
    )
    return await llm.complete(
        system_prompt(config.get("ruleset")), user_prompt, max_tokens=plan_token_cap()
    )
