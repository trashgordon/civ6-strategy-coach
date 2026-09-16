"""The one place we talk to a model.

Everything goes through LiteLLM so the provider is a matter of the MODEL env var, not a
code change. Nothing here is Anthropic-specific.
"""

import os

from . import config


class LLMError(RuntimeError):
    """Something went wrong talking to the model — message is safe to show the user."""


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


async def complete(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    hint = missing_key_hint()
    if hint:
        raise LLMError(
            f"{hint} isn't set, but MODEL is {config.model()}. "
            f"Add it to your .env and restart."
        )

    # Imported lazily: litellm is slow to import, and startup shouldn't pay for it.
    import litellm

    try:
        response = await litellm.acompletion(
            model=config.model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
        )
    except Exception as exc:  # LiteLLM raises a wide family of provider errors
        raise LLMError(f"The model call failed: {exc}") from exc

    text = _extract_text(response)
    if not text:
        raise LLMError("The coach came back empty-handed. Try again.")
    return text


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
