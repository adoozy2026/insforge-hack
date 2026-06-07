"""Golden tests for the tftcentral.co.uk deterministic extractor.

Each subdirectory under tests/fixtures/extractors/tftcentral/ is one
sample:
    input.html      — raw page HTML the extractor sees
    spec.json       — the user's shopping spec for the run
    expected.json   — facts the extractor must produce, byte-exact
    meta.json       — optional; {"url": "..."} overrides the default URL

To add a new sample, drop a directory with those files and either
register the URL in `DEFAULT_URL_BY_DIR` below or include `meta.json`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tools.extractors.tftcentral import extract_from_html

FIXTURES = Path(__file__).parent / "fixtures" / "extractors" / "tftcentral"

DEFAULT_URL_BY_DIR = {
    "lg-32gs95ue": "https://tftcentral.co.uk/reviews/lg-32gs95ue",
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
def test_tftcentral_extractor_golden(fixture_dir: Path) -> None:
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
    out = extract_from_html(
        "<html><body>not a review</body></html>",
        "https://tftcentral.co.uk/reviews/whatever",
        {},
    )
    assert isinstance(out, dict)
    assert out["title"] is None
    assert out["price_cents"] is None
    # Transactional fields are always None for this review site.
    assert out["seller"] is None
    assert out["shipping_cost_cents"] is None


def test_extractor_handles_empty_html() -> None:
    out = extract_from_html("", "https://tftcentral.co.uk/reviews/x", {})
    assert isinstance(out, dict)
    assert out["title"] is None
    assert out["canonical_attrs"] == {}


def test_extractor_falls_back_to_url_slug_for_brand_model() -> None:
    # No <h1>, no og: meta — only the URL gives us a hint.
    out = extract_from_html(
        "<html><head></head><body></body></html>",
        "https://tftcentral.co.uk/reviews/samsung-odyssey-g8",
        {},
    )
    assert out["canonical_attrs"] == {"brand": "Samsung", "model": "ODYSSEY-G8"}


def test_extractor_handles_two_word_brand() -> None:
    out = extract_from_html(
        '<h1 class="cm-entry-title">Cooler Master GP27Q</h1>',
        "https://tftcentral.co.uk/reviews/cooler-master-gp27q",
        {},
    )
    assert out["title"] == "Cooler Master GP27Q"
    assert out["canonical_attrs"] == {"brand": "Cooler Master", "model": "GP27Q"}


def test_extractor_strips_review_suffix_from_og_title() -> None:
    # Only og:title is present (no h1, no JSON-LD Article).
    html = (
        '<html><head>'
        '<meta property="og:title" content="ASUS PG32UCDP Review - TFTCentral" />'
        '</head><body></body></html>'
    )
    out = extract_from_html(html, "https://tftcentral.co.uk/reviews/asus-pg32ucdp", {})
    assert out["title"] == "ASUS PG32UCDP"
    assert out["canonical_attrs"] == {"brand": "ASUS", "model": "PG32UCDP"}
