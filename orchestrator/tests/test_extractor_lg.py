"""Golden tests for the lg.com deterministic extractor.

Each subdirectory under tests/fixtures/extractors/lg/ is one sample:
    input.html      — raw page HTML the extractor sees
    spec.json       — the user's shopping spec for the run
    expected.json   — facts the extractor must produce, byte-exact
    meta.json       — optional; {"url": "..."} overrides the default URL
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tools.extractors.lg import extract_from_html

FIXTURES = Path(__file__).parent / "fixtures" / "extractors" / "lg"

DEFAULT_URL_BY_DIR = {
    "32gs95ue-b-gaming-monitor": (
        "https://www.lg.com/us/monitors/lg-32gs95ue-b-gaming-monitor"
    ),
}


def _fixture_dirs() -> list[Path]:
    if not FIXTURES.exists():
        return []
    return sorted(p for p in FIXTURES.iterdir() if p.is_dir())


@pytest.mark.parametrize(
    "fixture_dir",
    _fixture_dirs(),
    ids=lambda p: p.name,
)
def test_lg_extractor_golden(fixture_dir: Path) -> None:
    html = (fixture_dir / "input.html").read_text(encoding="utf-8")
    spec = json.loads((fixture_dir / "spec.json").read_text(encoding="utf-8"))
    expected = json.loads((fixture_dir / "expected.json").read_text(encoding="utf-8"))

    meta_path = fixture_dir / "meta.json"
    if meta_path.exists():
        url = json.loads(meta_path.read_text(encoding="utf-8"))["url"]
    else:
        url = DEFAULT_URL_BY_DIR.get(fixture_dir.name)
        assert url, (
            f"no URL configured for fixture {fixture_dir.name}; add meta.json or "
            "an entry to DEFAULT_URL_BY_DIR"
        )

    actual = extract_from_html(html, url, spec)
    assert actual == expected


def test_extractor_never_raises_on_garbage() -> None:
    # The contract says: always return a dict, never raise.
    out = extract_from_html(
        "<html><body>not a product</body></html>",
        "https://www.lg.com/us/monitors/lg-foo",
        {},
    )
    assert isinstance(out, dict)
    assert out["price_cents"] is None
    assert out["seller"] == "LG"


def test_extractor_handles_empty_html() -> None:
    out = extract_from_html("", "https://www.lg.com/us/monitors/lg-foo", {})
    assert isinstance(out, dict)
    assert out["title"] is None
    assert out["price_cents"] is None
