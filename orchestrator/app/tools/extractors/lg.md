# lg.com — browser-agent hints

These hints are injected into the configurator's system prompt when the
deterministic `lg.py` extractor returns thin results (e.g. a regional
mis-route, or a page that ships without the JSON-LD Product schema).

## URL shapes

- **Product PDPs** — `/us/<category>/lg-<sku>-<slug>`, e.g.
  `/us/monitors/lg-32gs95ue-b-gaming-monitor`. The SKU embedded in the
  path (`32gs95ue-b`) is the canonical model number.
- **Series listing pages** — `/us/<series>-monitors` etc. Not PDPs; skip.
- **/global, /uk, /de, …** — non-US locales have different pricing and
  inventory. Always prefer `/us/...` when the spec is US-targeted.

## Selectors that work

- JSON-LD: `script[type="application/ld+json"]` carries a `@type: Product`
  schema with `name`, `brand.name`, `description`, `offers.price`,
  `offers.priceCurrency`, `offers.availability`, `offers.itemCondition`.
  The deterministic extractor reads this directly.
- Visible price: `.Product-Price .Product-MainPrice` (current) and
  `.Product-Price .Product-DiscountPrice` (sale). React hydrates these
  late — `MuiSkeleton-root` siblings appear first, so wait for the
  skeleton class to disappear before reading.
- "Add to cart" button: `button[data-testid="add-to-cart"]` /
  `button[aria-label*="Add to Cart"]`. Disabled when OOS.
- Out-of-stock: JSON-LD `offers.availability` is
  `https://schema.org/OutOfStock`. The "Notify Me" CTA replaces "Add to
  Cart" in the DOM.
- Image gallery thumbnail: `og:image` meta tag points to
  `media.us.lg.com/transform/ecomm-PDPGalleryThumbnail-...` — that's the
  one to use, not the `image` field on the Product JSON-LD which
  occasionally points to a 360° viewer HTML page.

## Meta tags

LG ships open-graph tags with `name="og:title"` instead of the standard
`property="og:title"`. If you parse with a strict parser, accept both.

## Variant pickers / configurators

Most monitors and appliances are single-SKU PDPs — no configurator.
TVs and laptops use radio-button size pickers:

- Size radio: `input[name="size"]` with labels like "55 inch", "65 inch".
  Match `spec.must_haves` size strings on the visible label text.
- Color radio (appliances): `input[name="color"]`. Each variant has its
  own URL; selecting one triggers a soft navigation. Wait for the new
  JSON-LD to load before re-extracting price.

## Pitfalls

- The strikethrough "was" price lives in the JSON-LD as a separate
  `UnitPriceSpecification` with `priceType: StrikethroughPrice`. The
  current price is `offers.price` — don't read the priceSpecification
  array as the live price.
- `priceCurrency: USD` is implicit; if you see `KRW` or `GBP`, the page
  is in the wrong locale — bail and re-route to `/us/...`.
- LG occasionally interstitials with a country/region picker
  (`/choose-country-region`). Treat that the same as a regional
  mis-route; retry with the canonical `/us/...` URL.
- No login wall or captcha on PDPs as of 2026-Q2. If you do hit one,
  it's an A/B test — refresh once before falling back to the agent.
- The product `description` in JSON-LD is identical to the
  `<meta name="description">` tag — either source is fine; the meta tag
  is usually shorter and cleaner.
