# newegg.com — extractor hints

These notes are appended to the browser-agent's system prompt when the
deterministic extractor falls through. They're written for the *fallback*
path, so they describe quirks the deterministic code already handles plus
the ones it can't.

## Page layouts

Newegg has two relevant DOMs and the extractor decides between them by
selector probe (not URL):

- **List / search**: `.item-cell` repeats once per result. Each cell has
  `.item-title` (a link), `.item-features` (bullet list of specs),
  `.price-current` (with the dollars in `<strong>` and cents in `<sup>`),
  `.price-ship` (often literally "Free Shipping"), and an `img` whose real
  src may be on `data-src` until lazy-load promotes it. The product image
  is the first non-svg, non-data-uri `img` inside the cell — do NOT use
  `og:image`, which on list pages is the Newegg logo.
- **Product**: `h1.product-title` / `.product-title` for the name,
  `.price-current` for the configured price, `.product-bullets` /
  `.product-spec` for the spec sheet, `.product-seller` for marketplace
  third-parties (text shape "Sold by: <name>"). Default seller is
  `"Newegg"` when no third-party block is present.

## Price parsing

Prices split across `<strong>` and `<sup>` concatenate via `innerText` as
`"829.99"` with no dollar sign. Match `\$?\s*([\d,]+)(?:\.(\d{1,2}))?` and
treat both groups as digits. If you see `$829.99` on the same node, the
same regex still works.

## Matching `spec.must_haves`

On list pages, Newegg returns lots of tangentially-related SKUs (cables,
monitor arms, refurb of last year's model). Filter cells by:

1. drop anything where `.price-current` parses above `spec.budget_cents`;
2. score the remaining cells by the number of `must_haves` substrings
   that appear (case-insensitive) in `title + item-features`;
3. break ties on lower price.

Marketing phrases the user typed verbatim ("latest model", "newest gen")
won't appear in Newegg's bullets — treat must_have hits as a soft score,
not a hard filter, and fall back to the cheapest within-budget item if no
cell scores above zero.

## Shipping & condition

- `.price-ship` text is the truth source for shipping cost. Treat any
  text containing the word "free" (case-insensitive) as `0` cents.
- List pages don't surface condition; default to `"new"`. If you see
  "Refurbished", "Open Box", or "Used" in the title or in a badge above
  the price, override.

## Configurator / popups (browser-agent only)

When falling through to the browser agent:

- Newegg occasionally interstitials a region/currency picker (`#NeweggRegionPopupModal`)
  on first visit. Dismiss with the "Continue" button — selecting a region
  reloads the page and loses the search query.
- "Sign in to see price" overlays appear on a small subset of B2B SKUs;
  treat as `give_up` — no public price exists.
- The price never lives behind a configurator dropdown on the consumer
  storefront. If `.price-current` is empty after `domcontentloaded`,
  wait for `.item-cell` (list) or `.product-buy-box` (PDP) once, then
  give up rather than clicking around.

## Captcha

Newegg uses a PerimeterX challenge served via `_px*` cookies. There's no
known click-through; if you land on a `/access-denied` redirect, return
`give_up` immediately.
