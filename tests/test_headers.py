"""Tidying decorated headers back to the thirteen the app renders by name."""

import pytest

from backend.generation import tidy_headers


@pytest.mark.parametrize("written, tidied", [
    ("## Timing Benchmarks (Standard speed)\n- T25", "## Timing Benchmarks\n\nStandard speed.\n- T25"),
    ("## What Goes Wrong: early war\n- x", "## What Goes Wrong\n\nEarly war.\n- x"),
    ("## Dedications — all ages\n- x", "## Dedications\n\nAll ages.\n- x"),
    ("## 3. Civic path\n- x", "## Civic Path\n- x"),
    ("## tech path\n- x", "## Tech Path\n- x"),
])
def test_decorated_headers_are_put_back(written, tidied):
    assert tidy_headers(written) == tidied


@pytest.mark.parametrize("header", [
    "## Timing Benchmarks",          # already right
    "## Governors & Titles",         # a different header, not decoration
    "## Notes",                      # unknown; left for the eval to report
])
def test_other_headers_are_left_alone(header):
    assert tidy_headers(f"{header}\n- x") == f"{header}\n- x"


def _plan(order):
    return "\n\n".join(f"## {h}\n- {h.lower()} advice" for h in order) + "\n"


def test_sections_are_put_back_in_the_prompt_s_order():
    from backend import prompts
    expected = prompts.expected_headers()
    moved = expected[:9] + ["Timing Benchmarks", "What Goes Wrong", "Religious Beliefs", "The Playbook"]
    assert tidy_headers(_plan(moved)) == _plan(expected)


def test_order_is_restored_after_a_decorated_header_is_fixed():
    from backend import prompts
    expected = prompts.expected_headers()
    moved = expected[:9] + ["Timing Benchmarks", "What Goes Wrong", "Religious Beliefs", "The Playbook"]
    text = _plan(moved).replace("## Timing Benchmarks\n", "## Timing Benchmarks (Marathon)\n")
    tidied = tidy_headers(text)
    assert [line for line in tidied.splitlines() if line.startswith("## ")] == [f"## {h}" for h in expected]
    assert "## Timing Benchmarks\n\nMarathon.\n- timing benchmarks advice" in tidied


def test_an_in_order_plan_is_untouched_byte_for_byte():
    from backend import prompts
    text = "Preamble line.\n\n" + _plan(prompts.expected_headers())
    assert tidy_headers(text) == text


@pytest.mark.parametrize("names", [
    ["Tech Path", "Civ & Leader", "Notes"],            # an unknown header
    ["Tech Path", "Civ & Leader", "Tech Path"],        # a repeated one
])
def test_an_unusual_plan_is_left_in_its_own_order(names):
    text = _plan(names)
    assert tidy_headers(text) == text


def test_text_before_the_first_header_stays_first():
    text = "Intro.\n\n## Tech Path\n- a\n\n## Civ & Leader\n- b\n"
    assert tidy_headers(text) == "Intro.\n\n## Civ & Leader\n- b\n\n## Tech Path\n- a\n"


def test_a_bracket_naming_a_missing_section_is_that_section():
    # Seen in an eval: Religious Beliefs written as "Wonders (Religious Beliefs)".
    text = "## Wonders\n- w\n\n## Wonders (Religious Beliefs)\n- not a religious build\n"
    assert tidy_headers(text) == "## Wonders\n- w\n\n## Religious Beliefs\n- not a religious build\n"


def test_a_bracket_naming_a_section_that_exists_is_just_decoration():
    text = "## Wonders (Religious Beliefs)\n- w\n\n## Religious Beliefs\n- r\n"
    assert tidy_headers(text).startswith("## Wonders\n\nReligious Beliefs.\n- w")
