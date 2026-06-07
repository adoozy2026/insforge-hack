"""Golden-file tests for deterministic extractors.

Each fixture directory under ``tests/fixtures/extractors/<domain>/`` holds
an ``input.html``, ``spec.json``, and ``expected.json``. We load the HTML
into a Playwright page (intercepted at the network level so chromium never
actually leaves the box) and assert the extractor's output matches the
golden.

Fields not present in ``expected.json`` are ignored, so a fixture can
assert only the subset of the listing it cares about.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

_FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "extractors"


def _domain_to_module(domain: str) -> str:
    return domain.replace(".", "_").replace("-", "_")


def _discover_goldens() -> list[tuple[str, Path]]:
    if not _FIXTURES_ROOT.exists():
        return []
    cases: list[tuple[str, Path]] = []
    for d in sorted(_FIXTURES_ROOT.iterdir()):
        if not d.is_dir():
            continue
        if not (d / "input.html").exists():
            continue
        if not (d / "expected.json").exists():
            continue
        cases.append((d.name, d))
    return cases


_GOLDENS = _discover_goldens()


@pytest.mark.parametrize(
    "domain,fix_dir",
    _GOLDENS,
    ids=[d for d, _ in _GOLDENS] or ["(no fixtures)"],
)
async def test_extractor_golden(domain: str, fix_dir: Path, page) -> None:
    module_name = f"app.tools.extractors.{_domain_to_module(domain)}"
    mod = importlib.import_module(module_name)

    html = (fix_dir / "input.html").read_text()
    spec_path = fix_dir / "spec.json"
    spec = json.loads(spec_path.read_text()) if spec_path.exists() else {}
    expected = json.loads((fix_dir / "expected.json").read_text())

    # Load the fixture HTML directly. We deliberately don't hit the network
    # — the extractor must work off DOM selectors only. Extractors that want
    # to branch on URL should accept a ``spec.url`` hint instead of reading
    # ``page.url`` (which would be ``about:blank`` here).
    await page.set_content(html, wait_until="domcontentloaded")

    result = await mod.extract(page, spec)

    assert isinstance(result, dict), f"extract returned {type(result).__name__}"
    for key, want in expected.items():
        assert key in result, f"{domain}: missing field {key!r}"
        got = result[key]
        assert got == want, (
            f"{domain}.{key}: got {got!r}, expected {want!r}"
        )
