"""lg.com — deterministic PDP extractor.

LG USA product pages (`/us/.../<sku>...`) embed a full JSON-LD Product
schema directly in the static HTML — name, brand, price, condition,
availability, and description are all there before any React hydration
runs. That's the data the browser-agent loop was spending 15-45s to
re-discover. This module lifts it directly.

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
# LG ships og:* meta tags with name="og:foo" (non-standard) — accept both.
_OG_META_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:([a-z_]+)["\'][^>]+content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_META_DESCRIPTION_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
# LG product names end with " - <MODEL>", e.g.
# "... Gaming Monitor with Pixel Sound - 32GS95UE-B".
_MODEL_FROM_NAME_RE = re.compile(r"-\s+([A-Z0-9]+(?:-[A-Z0-9]+)*)\s*$")

_CONDITION_MAP = {
    "newcondition": "new",
    "refurbishedcondition": "refurbished",
    "usedcondition": "used",
    "damagedcondition": "used",
}


async def extract(page: Page, spec: dict) -> dict:
    """Read the loaded LG PDP and return ListingFacts-shaped dict."""
    try:
        await page.wait_for_selector(
            'script[type="application/ld+json"]',
            timeout=8000,
            state="attached",
        )
    except Exception:
        pass
    try:
        html = await page.content()
        url = page.url
    except Exception as e:
        log.warning("lg extract: page.content() failed: %s", e)
        return _empty()
    try:
        return extract_from_html(html, url, spec)
    except Exception as e:
        log.warning("lg extract: parse failed: %s", e)
        return _empty()


def extract_from_html(html: str, url: str, spec: dict | None = None) -> dict:
    """Pure HTML → facts. Safe to call from tests without a browser."""
    out = _empty()
    if not html:
        return out

    out["seller"] = "LG"

    product = _find_product_jsonld(html)
    og = {k.lower(): _html.unescape(v) for k, v in _OG_META_RE.findall(html)}

    if og.get("title"):
        out["title"] = og["title"]
    elif product and product.get("name"):
        out["title"] = _html.unescape(str(product["name"]))

    if og.get("image"):
        out["image_url"] = og["image"]
    elif product and product.get("image"):
        img = product["image"]
        candidate = img if isinstance(img, str) else (img[0] if img else None)
        # JSON-LD on LG sometimes points to a 360° viewer HTML page rather
        # than an actual image — only accept it if it looks like a real image.
        if candidate and not candidate.lower().endswith(".html"):
            out["image_url"] = candidate

    desc = og.get("description")
    if not desc:
        m = _META_DESCRIPTION_RE.search(html)
        if m:
            desc = _html.unescape(m.group(1))
    if not desc and product and product.get("description"):
        desc = str(product["description"])
    if desc:
        out["description_summary"] = desc[:300]

    if product:
        offer = _first_offer(product.get("offers"))
        if offer:
            price = offer.get("price")
            if price is not None:
                try:
                    out["price_cents"] = round(float(price) * 100)
                except (TypeError, ValueError):
                    pass

            cond_key = str(offer.get("itemCondition") or "").rsplit("/", 1)[-1].lower()
            if cond_key in _CONDITION_MAP:
                out["condition"] = _CONDITION_MAP[cond_key]

            ship = offer.get("shippingDetails")
            rate = (ship or {}).get("shippingRate") if isinstance(ship, dict) else None
            if isinstance(rate, dict) and "value" in rate:
                try:
                    out["shipping_cost_cents"] = round(float(rate["value"]) * 100)
                except (TypeError, ValueError):
                    pass

            ret = offer.get("hasMerchantReturnPolicy")
            if isinstance(ret, dict):
                days = ret.get("merchantReturnDays")
                if days is not None:
                    try:
                        out["return_policy"] = f"{int(days)}-day returns"
                    except (TypeError, ValueError):
                        pass

    if out["condition"] is None:
        # LG sells new product by default; treat undecorated PDPs as "new".
        out["condition"] = "new"

    out["canonical_attrs"] = _canonical_attrs(url, product)
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


def _find_product_jsonld(html: str) -> dict | None:
    for raw in _JSON_LD_RE.findall(html):
        try:
            data = json.loads(raw.strip())
        except Exception:
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict) and str(d.get("@type", "")).lower() == "product":
                return d
    return None


def _first_offer(offers: Any) -> dict | None:
    if isinstance(offers, dict):
        return offers
    if isinstance(offers, list):
        for o in offers:
            if isinstance(o, dict):
                return o
    return None


def _canonical_attrs(url: str, product: dict | None) -> dict:
    attrs: dict[str, Any] = {"brand": "LG"}

    if product:
        brand = product.get("brand")
        if isinstance(brand, dict) and brand.get("name"):
            attrs["brand"] = str(brand["name"])
        elif isinstance(brand, str) and brand:
            attrs["brand"] = brand

        offer = _first_offer(product.get("offers"))
        sku = product.get("sku") or product.get("mpn")
        if not sku and offer:
            sku = offer.get("sku") or offer.get("mpn")
        if not sku:
            name = product.get("name")
            if isinstance(name, str):
                m = _MODEL_FROM_NAME_RE.search(name)
                if m:
                    sku = m.group(1)
        if sku:
            attrs["model"] = str(sku).upper()

    return attrs
