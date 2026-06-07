"""tftcentral.co.uk — deterministic review-page extractor.

TFTCentral is a monitor *review* site, not a retailer. Pages under
`/reviews/<slug>` are long-form articles with no configurator, no
checkout, and no listed price for the reviewed model — affiliate
"buy" links scattered through the article point at unrelated
recommended products. The Gemini browser-agent loop was repeatedly
scrolling these pages looking for prices that don't exist, then
giving up and synthesising title/brand/model from the article itself.

Everything that loop ends up extracting (product title, hero image,
brand, model, one-line description) is already in the static HTML:

    - <h1 class="cm-entry-title">           — product name
    - <meta property="og:image" content=…>  — hero image
    - <meta name="description" content=…>   — one-line summary
    - JSON-LD `Article.headline`            — title fallback

For transactional fields (price_cents, condition, seller,
shipping_*, return_policy) we deliberately return None — letting
the orchestrator route to a real retailer for the buy step instead
of pretending we found something.

Public surface:
    extract(page, spec)              — async, used by the extractor pool
    extract_from_html(html, url, …)  — pure helper, used by golden tests
"""

from __future__ import annotations

import html as _html
import json
import logging
import re
from typing import Any

from playwright.async_api import Page

log = logging.getLogger(__name__)


_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_OG_META_RE = re.compile(
    r'<meta[^>]+property=["\']og:([a-z:]+)["\'][^>]+content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_NAME_META_RE = re.compile(
    r'<meta[^>]+name=["\']([a-z:]+)["\'][^>]+content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_ENTRY_TITLE_RE = re.compile(
    r'<h1[^>]+class=["\'][^"\']*cm-entry-title[^"\']*["\'][^>]*>(.*?)</h1>',
    re.IGNORECASE | re.DOTALL,
)
_GENERIC_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_URL_SLUG_RE = re.compile(r"/reviews/([^/?#]+)", re.IGNORECASE)

# Brands known to ship monitors / TVs reviewed on TFTCentral. Used as a
# hint so the brand parser handles two-word brands ("Cooler Master")
# and brands whose product codes are all-digits ("AOC U28G2XU").
_KNOWN_BRANDS: tuple[tuple[str, ...], ...] = (
    ("cooler", "master"),
    ("lg",),
    ("samsung",),
    ("asus",),
    ("msi",),
    ("dell",),
    ("alienware",),
    ("aoc",),
    ("acer",),
    ("benq",),
    ("philips",),
    ("viewsonic",),
    ("gigabyte",),
    ("hp",),
    ("lenovo",),
    ("innocn",),
    ("ktc",),
    ("corsair",),
    ("razer",),
    ("eve",),
    ("xiaomi",),
    ("huawei",),
    ("sony",),
    ("apple",),
    ("nzxt",),
    ("iiyama",),
    ("hisense",),
    ("tcl",),
    ("sharp",),
    ("panasonic",),
)


async def extract(page: Page, spec: dict) -> dict:
    """Read the loaded TFTCentral review page and return facts."""
    try:
        await page.wait_for_selector(
            'h1.cm-entry-title, meta[property="og:title"]',
            timeout=8000,
            state="attached",
        )
    except Exception:
        pass
    try:
        html = await page.content()
        url = page.url
    except Exception as e:
        log.warning("tftcentral extract: page.content() failed: %s", e)
        return _empty()
    try:
        return extract_from_html(html, url, spec)
    except Exception as e:
        log.warning("tftcentral extract: parse failed: %s", e)
        return _empty()


def extract_from_html(html: str, url: str, spec: dict | None = None) -> dict:
    """Pure HTML → facts. Safe to call from tests without a browser."""
    out = _empty()
    if not html:
        return out

    og = {k.lower(): _html.unescape(v) for k, v in _OG_META_RE.findall(html)}
    named = {k.lower(): _html.unescape(v) for k, v in _NAME_META_RE.findall(html)}
    article = _find_article_jsonld(html)

    title = _extract_title(html, og, article)
    if title:
        out["title"] = title

    if og.get("image"):
        out["image_url"] = og["image"]
    elif article and article.get("thumbnailUrl"):
        out["image_url"] = str(article["thumbnailUrl"])

    desc = named.get("description") or og.get("description")
    if not desc and article:
        desc = article.get("description") or article.get("headline")
    if desc:
        out["description_summary"] = str(desc)[:300]

    out["canonical_attrs"] = _canonical_attrs(title, url)
    return out


def _empty() -> dict:
    return {
        "title": None,
        "price_cents": None,
        "condition": None,
        "seller": None,
        "shipping_cost_cents": None,
        "shipping_speed": None,
        "return_policy": None,
        "image_url": None,
        "description_summary": None,
        "canonical_attrs": {},
    }


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _extract_title(html: str, og: dict[str, str], article: dict | None) -> str | None:
    m = _ENTRY_TITLE_RE.search(html)
    if m:
        raw = _normalize_ws(_html.unescape(_strip_tags(m.group(1))))
        if raw:
            return raw
    if article and article.get("headline"):
        return _normalize_ws(str(article["headline"]))
    og_title = og.get("title")
    if og_title:
        # og:title is usually "<product> Review - TFTCentral"; trim the suffix.
        return _clean_review_suffix(og_title)
    # Last-resort: any <h1>.
    m = _GENERIC_H1_RE.search(html)
    if m:
        raw = _normalize_ws(_html.unescape(_strip_tags(m.group(1))))
        if raw:
            return _clean_review_suffix(raw)
    return None


def _clean_review_suffix(s: str) -> str:
    # Strip trailing " Review - TFTCentral" / " - TFTCentral".
    s = re.sub(r"\s*Review\s*-\s*TFTCentral\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*-\s*TFTCentral\s*$", "", s, flags=re.IGNORECASE)
    return s.strip()


def _find_article_jsonld(html: str) -> dict | None:
    for raw in _JSON_LD_RE.findall(html):
        try:
            data = json.loads(raw.strip())
        except Exception:
            continue
        # Yoast emits {"@graph": [...]} with multiple node types.
        graph = data.get("@graph") if isinstance(data, dict) else None
        candidates = graph if isinstance(graph, list) else (
            data if isinstance(data, list) else [data]
        )
        for d in candidates:
            if isinstance(d, dict) and str(d.get("@type", "")).lower() == "article":
                return d
    return None


def _canonical_attrs(title: str | None, url: str) -> dict:
    attrs: dict[str, Any] = {}
    brand, model = _split_brand_model(title, url)
    if brand:
        attrs["brand"] = brand
    if model:
        attrs["model"] = model
    return attrs


def _split_brand_model(title: str | None, url: str) -> tuple[str | None, str | None]:
    if not title:
        return _brand_model_from_slug(url)
    tokens = title.split()
    if not tokens:
        return _brand_model_from_slug(url)

    lower = [t.lower().strip(".,") for t in tokens]
    for prefix in _KNOWN_BRANDS:
        plen = len(prefix)
        if len(lower) >= plen and tuple(lower[:plen]) == prefix:
            brand = " ".join(tokens[:plen])
            model = " ".join(tokens[plen:]).strip()
            return _format_brand(brand), (model or None)

    # No known brand matched — fall back to "first token is brand, rest is model"
    # which is the consistent pattern on TFTCentral review titles.
    brand = tokens[0]
    model = " ".join(tokens[1:]).strip() or None
    return _format_brand(brand), model


def _brand_model_from_slug(url: str) -> tuple[str | None, str | None]:
    m = _URL_SLUG_RE.search(url or "")
    if not m:
        return None, None
    parts = m.group(1).split("-")
    if not parts:
        return None, None
    for prefix in _KNOWN_BRANDS:
        plen = len(prefix)
        if len(parts) >= plen and tuple(p.lower() for p in parts[:plen]) == prefix:
            brand = " ".join(parts[:plen])
            model = "-".join(parts[plen:]) or None
            return _format_brand(brand), (model.upper() if model else None)
    brand = parts[0]
    model = "-".join(parts[1:]) or None
    return _format_brand(brand), (model.upper() if model else None)


def _format_brand(s: str) -> str:
    # Short acronyms (LG, MSI, ASUS, AOC, HP, BenQ, etc.) — upper-case unless
    # they're a known mixed-case brand. Multi-word brands get title-cased.
    parts = s.split()
    out = []
    for p in parts:
        low = p.lower()
        if low == "benq":
            out.append("BenQ")
        elif low == "viewsonic":
            out.append("ViewSonic")
        elif low == "alienware":
            out.append("Alienware")
        elif low in {"cooler", "master", "samsung", "apple", "philips", "lenovo",
                      "gigabyte", "corsair", "razer", "xiaomi", "huawei", "sony",
                      "acer", "iiyama", "hisense", "sharp", "panasonic", "innocn",
                      "eve", "nzxt"}:
            out.append(p.capitalize())
        elif low in {"tcl"}:
            out.append(p.upper())
        elif len(p) <= 5:
            out.append(p.upper())
        else:
            out.append(p.capitalize())
    return " ".join(out)
