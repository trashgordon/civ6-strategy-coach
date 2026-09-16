"""The LLM layer: usage extraction, and diagnosing an empty response.

The empty-response case is a real bug that shipped: Claude Sonnet 5 has reasoning on by
default, so a 2000-token cap was consumed entirely by reasoning and the user got
"The coach came back empty-handed" with nothing to act on.
"""

import pytest

from backend import llm


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content, finish_reason="stop"):
        self.message = FakeMessage(content)
        self.finish_reason = finish_reason


class FakeUsage:
    def __init__(self, prompt_tokens=None, completion_tokens=None):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class FakeResponse:
    def __init__(self, content, finish_reason="stop", usage=None):
        self.choices = [FakeChoice(content, finish_reason)]
        self.usage = usage


def test_reasoning_that_ate_the_budget_says_so():
    """finish_reason 'length' with no text names the cause and the knob to turn."""
    response = FakeResponse(None, finish_reason="length")

    message = llm._empty_response_reason(response, max_tokens=4000)

    assert "4000-token budget" in message
    assert "reasoning" in message.lower()
    assert "REASONING_EFFORT" in message
    # Not the old undebuggable message.
    assert "empty-handed" not in message


def test_a_genuinely_empty_response_still_says_try_again():
    response = FakeResponse("", finish_reason="stop")
    assert "empty-handed" in llm._empty_response_reason(response, max_tokens=4000)


def test_reasoning_effort_defaults_to_low():
    """Left unbounded, a reasoning model spends the whole budget thinking."""
    assert llm.REASONING_EFFORT == "low"


@pytest.mark.parametrize(
    "content, expected",
    [
        ("  a plan  ", "a plan"),
        (None, ""),
        ([{"type": "text", "text": "block one"}, {"type": "text", "text": "two"}],
         "block one\ntwo"),
        # Thinking blocks must not be mistaken for the answer.
        ([{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "answer"}],
         "answer"),
    ],
)
def test_text_extraction_shapes(content, expected):
    assert llm._extract_text(FakeResponse(content)) == expected


def test_usage_extraction_handles_both_naming_conventions():
    assert llm._extract_usage(FakeResponse("x", usage=FakeUsage(10, 20))) == (10, 20)

    class InputOutputNames:
        input_tokens = 7
        output_tokens = 9

    response = FakeResponse("x")
    response.usage = InputOutputNames()
    assert llm._extract_usage(response) == (7, 9)

    # No usage reported at all is not an error.
    assert llm._extract_usage(FakeResponse("x", usage=None)) == (None, None)


def test_missing_key_hint_is_quiet_for_local_models(monkeypatch):
    monkeypatch.setenv("MODEL", "ollama/llama3.1")
    assert llm.missing_key_hint() is None

    monkeypatch.setenv("MODEL", "openai/gpt-5")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm.missing_key_hint() == "OPENAI_API_KEY"


# ------------------------------------------------------------- prompt caching


def test_a_short_system_prompt_is_not_cached():
    """Below the provider's minimum cacheable prefix, a breakpoint is pure overhead."""
    message = llm._system_message("short prompt", "anthropic/claude-sonnet-5")
    assert message == {"role": "system", "content": "short prompt"}


def test_a_long_system_prompt_gets_a_cache_breakpoint(monkeypatch):
    monkeypatch.setattr(llm, "_supports_caching", lambda model: True)
    big = "x" * (llm._MIN_CACHEABLE_CHARS + 1)

    message = llm._system_message(big, "anthropic/claude-sonnet-5")

    assert message["role"] == "system"
    assert message["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert message["content"][0]["text"] == big


def test_caching_is_skipped_on_providers_that_cannot_do_it(monkeypatch):
    """A local Ollama model would choke on a cache_control block."""
    monkeypatch.setattr(llm, "_supports_caching", lambda model: False)
    big = "x" * (llm._MIN_CACHEABLE_CHARS + 1)
    assert llm._system_message(big, "ollama/llama3.1")["content"] == big


def test_caching_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(llm, "_supports_caching", lambda model: True)
    monkeypatch.setenv("PROMPT_CACHE", "0")
    big = "x" * (llm._MIN_CACHEABLE_CHARS + 1)
    assert llm._system_message(big, "anthropic/claude-sonnet-5")["content"] == big


def test_cache_usage_is_read_from_the_response():
    class Usage:
        cache_creation_input_tokens = 5819
        cache_read_input_tokens = 0

    response = FakeResponse("plan")
    response.usage = Usage()
    assert llm._extract_cache_usage(response) == (5819, 0)


def test_cache_usage_falls_back_to_the_openai_shape():
    class Details:
        cached_tokens = 4096

    class Usage:
        prompt_tokens_details = Details()

    response = FakeResponse("plan")
    response.usage = Usage()
    assert llm._extract_cache_usage(response) == (None, 4096)


def test_missing_cache_reporting_is_not_an_error():
    assert llm._extract_cache_usage(FakeResponse("plan", usage=None)) == (None, None)
