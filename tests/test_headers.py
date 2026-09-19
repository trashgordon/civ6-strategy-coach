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
