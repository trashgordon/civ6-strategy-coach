"""Drafting a build plan: the one path both the API and the eval harness go through.

Kept separate from the endpoint so `evals/` measures exactly what the app sends — same
prompt assembly, same grounding, same token cap — rather than a copy that can drift.
"""

import os
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
    )
    return await llm.complete(
        system_prompt(config.get("ruleset")), user_prompt, max_tokens=plan_token_cap()
    )
