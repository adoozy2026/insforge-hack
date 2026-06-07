"""Test config — wires the orchestrator package onto sys.path and gives the
extractor tests a Playwright ``page`` fixture.

We launch a fresh chromium per test for simplicity (the session-scoped
variant requires a session-scoped event loop and pytest-asyncio's defaults
make that awkward). One golden takes ~1s of browser startup, so a handful
of fixtures is still well under any reasonable CI budget.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ORCHESTRATOR_ROOT = Path(__file__).resolve().parent.parent
if str(_ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_ORCHESTRATOR_ROOT))


@pytest.fixture
async def page():
    pw_mod = pytest.importorskip("playwright.async_api")
    async with pw_mod.async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception as e:
            pytest.skip(f"chromium unavailable: {e}")
        try:
            ctx = await browser.new_context()
            pg = await ctx.new_page()
            try:
                yield pg
            finally:
                await ctx.close()
        finally:
            await browser.close()
