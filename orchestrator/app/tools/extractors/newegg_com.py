"""Deterministic extractor for newegg.com.

Newegg's product listings render server-side in two layouts we hit:

  * Search/list pages (``/p/pl?d=<query>``) — a grid of ``.item-cell``
    containers, each with a title link, feature bullets, and a price node.
  * Product pages (``/p/<item>``) — a single product with ``.product-title``
    and one ``.price-current`` block.

Both expose the configured price right in the HTML, so we can skip the
browser-agent loop entirely. We pick between the two layouts by selector
probe rather than URL parsing, so the same extractor works for any Newegg
URL that lands on either DOM (catalog, deal hub, etc.).

On list pages, when ``spec.must_haves`` is provided we score each item by
the number of must-have substrings present in (title + feature bullets) and
prefer the highest-scoring item within ``spec.budget_cents``. Falling back
to the first within-budget item if nothing matches at all.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from playwright.async_api import Page

log = logging.getLogger(__name__)


_LIST_SELECTOR = ".item-cell"
_PRODUCT_TITLE_SELECTOR = "h1.product-title, .product-title"
_WAIT_MS = 6000


# Newegg renders prices as ``<strong>829</strong><sup>.99</sup>`` — innerText
# concatenates to ``829.99`` (no dollar sign). On product pages we sometimes
# see ``$829.99`` instead, so accept both.
_PRICE_RE = re.compile(r"\$?\s*([\d,]+)(?:\.(\d{1,2}))?")


def _parse_price_cents(text: str | None) -> int | None:
    if not text:
        return None
    cleaned = text.replace(",", "").replace("\xa0", " ").strip()
    m = _PRICE_RE.search(cleaned)
    if not m:
        return None
    dollars_str = m.group(1)
    if not dollars_str:
        return None
    dollars = int(dollars_str)
    cents = int((m.group(2) or "0").ljust(2, "0")[:2])
    return dollars * 100 + cents


def _parse_shipping_cents(text: str | None) -> int | None:
    if not text:
        return None
    low = text.lower()
    if "free" in low:
        return 0
    return _parse_price_cents(text)


def _must_haves(spec: dict[str, Any]) -> list[str]:
    raw = spec.get("must_haves") or []
    return [s for s in raw if isinstance(s, str) and s.strip()]


def _score_item(haystack: str, must_haves: list[str]) -> int:
    if not must_haves:
        return 0
    low = haystack.lower()
    return sum(1 for m in must_haves if m.lower() in low)


async def _safe_inner_text(el: Any) -> str | None:
    if el is None:
        return None
    try:
        t = await el.inner_text()
    except Exception:
        return None
    t = (t or "").strip()
    return t or None


async def _safe_attr(el: Any, attr: str) -> str | None:
    if el is None:
        return None
    try:
        v = await el.get_attribute(attr)
    except Exception:
        return None
    v = (v or "").strip()
    return v or None


async def _pick_image(el: Any) -> str | None:
    """Pick the best product image src from an item-cell or product-image
    block. Newegg lazy-loads via ``data-src`` then promotes to ``src``, so
    we read both. Skip svg/spacer placeholders."""
    if el is None:
        return None
    try:
        imgs = await el.query_selector_all("img")
    except Exception:
        return None
    for img in imgs:
        for attr in ("src", "data-src", "data-image"):
            src = await _safe_attr(img, attr)
            if not src:
                continue
            if src.startswith("data:"):
                continue
            if src.endswith(".svg"):
                continue
            return src
    return None


async def _features_summary(el: Any) -> str | None:
    """Newegg item cards expose feature bullets under ``.item-features``.
    Product pages mirror these as ``.product-bullets`` / ``.product-spec``.
    Join the bullet lines with `` | `` so the result is dense enough to
    drop into ``description_summary`` directly."""
    if el is None:
        return None
    for sel in (".item-features li", ".item-features", ".product-bullets li", ".product-bullets"):
        try:
            nodes = await el.query_selector_all(sel)
        except Exception:
            nodes = []
        if not nodes:
            continue
        lines: list[str] = []
        for n in nodes:
            t = await _safe_inner_text(n)
            if not t:
                continue
            # When we grab the container (not <li>) inner_text gives us
            # newline-joined bullets; split them out.
            for ln in t.splitlines():
                ln = ln.strip(" •*\u2022\t")
                if ln:
                    lines.append(ln)
        if lines:
            joined = " | ".join(lines)
            return joined[:400] or None
    return None


# ---- List-page branch ---------------------------------------------------


async def _extract_list_page(page: Page, spec: dict[str, Any]) -> dict[str, Any] | None:
    try:
        await page.wait_for_selector(_LIST_SELECTOR, timeout=_WAIT_MS)
    except Exception:
        return None

    cells = await page.query_selector_all(_LIST_SELECTOR)
    if not cells:
        return None

    must_haves = _must_haves(spec)
    budget = spec.get("budget_cents") if isinstance(spec.get("budget_cents"), int) else None

    scored: list[tuple[int, int, Any, str, int | None]] = []
    fallback: tuple[Any, str, int | None] | None = None

    for cell in cells:
        title_el = await cell.query_selector(".item-title")
        title = await _safe_inner_text(title_el)
        if not title:
            continue

        price_el = await cell.query_selector(".price-current")
        price = _parse_price_cents(await _safe_inner_text(price_el))

        if fallback is None and (budget is None or (price is not None and price <= budget)):
            fallback = (cell, title, price)

        if budget is not None and price is not None and price > budget:
            continue

        features_el = await cell.query_selector(".item-features")
        features_text = await _safe_inner_text(features_el) or ""
        score = _score_item(title + " " + features_text, must_haves)
        # Sort key: higher score first, then lower price first (so ties prefer
        # the cheaper option). Indexing via -score, price (None → +inf).
        price_key = price if price is not None else 10**12
        scored.append((-score, price_key, cell, title, price))

    chosen = None
    if scored:
        scored.sort(key=lambda t: (t[0], t[1]))
        # Only accept a positive-score match when must_haves were given.
        top = scored[0]
        if not must_haves or top[0] < 0:
            chosen = (top[2], top[3], top[4])

    if chosen is None:
        chosen = fallback

    if chosen is None:
        return None

    cell, title, price = chosen

    ship_el = await cell.query_selector(".price-ship")
    shipping = _parse_shipping_cents(await _safe_inner_text(ship_el))

    image_url = await _pick_image(cell)
    description = await _features_summary(cell)

    return {
        "title": title,
        "price_cents": price,
        "condition": "new",
        "seller": "Newegg",
        "shipping_cost_cents": shipping,
        "shipping_speed": None,
        "return_policy": None,
        "image_url": image_url,
        "description_summary": description,
        "canonical_attrs": {},
    }


# ---- Product-page branch ------------------------------------------------


async def _extract_product_page(page: Page, spec: dict[str, Any]) -> dict[str, Any] | None:
    try:
        await page.wait_for_selector(_PRODUCT_TITLE_SELECTOR, timeout=_WAIT_MS)
    except Exception:
        # Some product pages render the title inside a different wrapper;
        # don't bail just because the wait selector missed.
        pass

    title_el = await page.query_selector(_PRODUCT_TITLE_SELECTOR)
    title = await _safe_inner_text(title_el)
    if not title:
        return None

    price_el = await page.query_selector(".price-current, .product-price .price-current")
    price = _parse_price_cents(await _safe_inner_text(price_el))

    ship_el = await page.query_selector(".product-pane .price-ship, .price-ship")
    shipping = _parse_shipping_cents(await _safe_inner_text(ship_el))

    # Seller: marketplace third-parties surface as "Sold by: <name>". Default
    # to Newegg when the page doesn't contradict.
    seller = "Newegg"
    sold_by = await page.query_selector(".product-seller, .product-sold-by")
    sold_by_text = await _safe_inner_text(sold_by)
    if sold_by_text:
        m = re.search(r"sold by[:\s]+(.+)", sold_by_text, re.IGNORECASE)
        if m:
            seller = m.group(1).strip().splitlines()[0].strip() or "Newegg"

    image_url = await _pick_image(page)
    description = await _features_summary(page)

    return {
        "title": title,
        "price_cents": price,
        "condition": "new",
        "seller": seller,
        "shipping_cost_cents": shipping,
        "shipping_speed": None,
        "return_policy": None,
        "image_url": image_url,
        "description_summary": description,
        "canonical_attrs": {},
    }


# ---- Public entry point -------------------------------------------------


_EMPTY: dict[str, Any] = {
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


async def extract(page: Page, spec: dict) -> dict:
    """Return a ListingFacts-shaped dict for the current Newegg page.

    Always returns a dict; on any failure (timeout, missing selectors,
    Playwright disconnect) returns the all-null skeleton so the caller can
    fall back to the browser-agent configurator without special-casing
    exceptions.
    """
    out = dict(_EMPTY)
    try:
        # Choose branch by selector probe — works regardless of URL shape.
        try:
            list_probe = await page.query_selector(_LIST_SELECTOR)
        except Exception:
            list_probe = None
        data: dict[str, Any] | None
        if list_probe is not None:
            data = await _extract_list_page(page, spec or {})
        else:
            data = await _extract_product_page(page, spec or {})
        if data:
            out.update({k: data.get(k, out[k]) for k in out})
    except Exception as e:
        log.warning("newegg_com extractor failed: %s", e)
    return out
