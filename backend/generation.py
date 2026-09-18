"""Drafting a build plan: the one path both the API and the eval harness go through.

Kept separate from the endpoint so `evals/` measures exactly what the app sends — same
prompt assembly, same grounding, same token cap — rather than a copy that can drift.
"""

from typing import Any

from . import facts, llm, prompts

# The prompt caps the prose at ~1100 words, but a reasoning model spends tokens thinking
# before it writes any of that. Measured on Claude Sonnet 5 at REASONING_EFFORT=low: a
# ~1100-word plan lands around 2,900 output tokens. The cap leaves room for that without
# going so high that a non-streaming request risks an HTTP timeout — a 16,000-token
# attempt disconnected mid-call.
MAX_PLAN_TOKENS = 6000


def system_prompt() -> str:
    """The build prompt as actually sent, grounding included."""
    return prompts.build_system_prompt(facts.prompt_block())


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
    return await llm.complete(system_prompt(), user_prompt, max_tokens=MAX_PLAN_TOKENS)
