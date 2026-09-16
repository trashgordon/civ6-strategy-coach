"""The one place we talk to a model.

Everything goes through LiteLLM so the provider is a matter of the MODEL env var, not a
code change. Nothing here is Anthropic-specific — including the cost accounting, which
uses LiteLLM's own pricing map rather than hardcoded per-provider rates.
"""

import logging
import os
from dataclasses import dataclass

from . import config

log = logging.getLogger("civ6.llm")


class LLMError(RuntimeError):
    """Something went wrong talking to the model — message is safe to show the user."""


# Reasoning models (Claude Sonnet 5, Opus 5, o-series, Gemini thinking) burn output
# tokens on internal reasoning before writing a word of the answer. Left unbounded, a
# reasoning model spends the entire max_tokens budget thinking and returns empty text.
# LiteLLM's `reasoning_effort` is the provider-agnostic dial for that, so we keep it low:
# the coach's output is a deliberately short brief, not a proof.
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "low").strip().lower() or "low"


# Caching only pays for a prefix big enough to clear the provider's minimum (1024-4096
# tokens depending on model) and stable across calls. The system prompt clears that only
# once the game-facts block is attached; the bare prompt is far too small to bother with.
_MIN_CACHEABLE_CHARS = 8000


@dataclass(frozen=True)
class Completion:
    """A model response plus what it cost to get it.

    Token counts and cost are optional on purpose: a provider may not report usage, and
    LiteLLM's pricing map doesn't know every model. None means "we couldn't tell", which
    is different from 0.0 — a local Ollama model genuinely costs nothing.
    """

    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    # Prompt-cache accounting. None when the provider reports nothing; 0 is a real
    # answer meaning "cacheable request, but nothing was written or read this time".
    cache_write_tokens: int | None = None
    cache_read_tokens: int | None = None


# Provider prefix -> the env var LiteLLM expects for it. Only used to give a useful
# error message before we make a doomed call; LiteLLM reads the keys itself.
_KEY_HINTS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "azure": "AZURE_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "vertex_ai": "GOOGLE_APPLICATION_CREDENTIALS",
    "mistral": "MISTRAL_API_KEY",
    "groq": "GROQ_API_KEY",
    "cohere": "COHERE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "xai": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Providers that run locally and need no key at all.
_KEYLESS = {"ollama", "ollama_chat", "lm_studio", "vllm", "huggingface_local"}


def missing_key_hint() -> str | None:
    """The name of the API key env var this MODEL needs but doesn't have, if any."""
    model_name = config.model()
    provider = model_name.split("/", 1)[0] if "/" in model_name else model_name
    provider = provider.lower()
    if provider in _KEYLESS:
        return None
    env_var = _KEY_HINTS.get(provider)
    if env_var and not os.getenv(env_var):
        return env_var
    return None


async def complete(system_prompt: str, user_prompt: str, max_tokens: int) -> Completion:
    hint = missing_key_hint()
    if hint:
        raise LLMError(
            f"{hint} isn't set, but MODEL is {config.model()}. "
            f"Add it to your .env and restart."
        )

    # Imported lazily: litellm is slow to import, and startup shouldn't pay for it.
    import litellm

    # Any provider that doesn't understand a parameter we send gets it stripped rather
    # than erroring — the whole point of going through LiteLLM.
    litellm.drop_params = True

    model_name = config.model()
    try:
        response = await litellm.acompletion(
            model=model_name,
            messages=[
                _system_message(system_prompt, model_name),
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            reasoning_effort=REASONING_EFFORT,
        )
    except Exception as exc:  # LiteLLM raises a wide family of provider errors
        raise LLMError(f"The model call failed: {exc}") from exc

    text = _extract_text(response)
    if not text:
        raise LLMError(_empty_response_reason(response, max_tokens))

    prompt_tokens, completion_tokens = _extract_usage(response)
    cache_write, cache_read = _extract_cache_usage(response)
    return Completion(
        text=text,
        model=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=_extract_cost(response, model_name),
        cache_write_tokens=cache_write,
        cache_read_tokens=cache_read,
    )


def caching_enabled() -> bool:
    return os.getenv("PROMPT_CACHE", "1").strip().lower() not in {"0", "false", "no"}


def _supports_caching(model_name: str) -> bool:
    try:
        from litellm.utils import supports_prompt_caching

        return bool(supports_prompt_caching(model=model_name))
    except Exception:
        return False


def _system_message(system_prompt: str, model_name: str) -> dict:
    """The system turn, marked as a cache breakpoint when that's worth doing.

    The system prompt is byte-identical between generations once the facts block is
    attached, which makes it an ideal cache prefix. The volatile part — the player's
    configuration — lives in the user turn, after the breakpoint, so it never invalidates
    the cache.
    """
    if (
        not caching_enabled()
        or len(system_prompt) < _MIN_CACHEABLE_CHARS
        or not _supports_caching(model_name)
    ):
        return {"role": "system", "content": system_prompt}

    return {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }


def _extract_cache_usage(response) -> tuple[int | None, int | None]:
    """Tokens written to and read from the prompt cache, if the provider reports them."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, None

    def count(*names):
        for name in names:
            value = getattr(usage, name, None)
            if value is None and isinstance(usage, dict):
                value = usage.get(name)
            if isinstance(value, int):
                return value
        return None

    write = count("cache_creation_input_tokens")
    read = count("cache_read_input_tokens")
    if read is None:
        # OpenAI reports it nested under prompt_tokens_details.cached_tokens.
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", None)
            if isinstance(cached, int):
                read = cached
    return write, read


def _finish_reason(response) -> str:
    try:
        return response.choices[0].finish_reason or ""
    except (AttributeError, IndexError, KeyError, TypeError):
        return ""


def _empty_response_reason(response, max_tokens: int) -> str:
    """Say *why* nothing came back — "empty-handed" on its own is undebuggable."""
    if _finish_reason(response) == "length":
        return (
            f"The model used its entire {max_tokens}-token budget without finishing the "
            f"plan. If MODEL is a reasoning model, reasoning consumed the budget — lower "
            f"REASONING_EFFORT (currently {REASONING_EFFORT!r}) or raise the cap."
        )
    return "The coach came back empty-handed. Try again."


def _extract_text(response) -> str:
    """LiteLLM normalizes to the OpenAI shape, but be forgiving about it."""
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError):
        return ""
    if isinstance(content, str):
        return content.strip()
    # Some providers hand back a list of content blocks.
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") in (None, "text")
        ]
        return "\n".join(part for part in parts if part).strip()
    return ""


def _extract_usage(response) -> tuple[int | None, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, None

    def count(*names):
        for name in names:
            value = getattr(usage, name, None)
            if value is None and isinstance(usage, dict):
                value = usage.get(name)
            if isinstance(value, int):
                return value
        return None

    return count("prompt_tokens", "input_tokens"), count(
        "completion_tokens", "output_tokens"
    )


def _extract_cost(response, model_name: str) -> float | None:
    """Dollar cost from LiteLLM's pricing map.

    Never allowed to fail the request: an unpriced model raises inside LiteLLM, and a
    missing price is not a reason to throw away a plan the user already paid for.
    """
    import litellm

    try:
        cost = litellm.completion_cost(completion_response=response, model=model_name)
    except Exception as exc:
        log.debug("no cost available for %s: %s", model_name, exc)
        return None
    return float(cost) if cost is not None else None
