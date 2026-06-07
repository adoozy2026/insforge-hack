# tftcentral.co.uk — browser-agent hints

These hints are injected into the configurator's system prompt when
the deterministic `tftcentral.py` extractor can't satisfy the spec
on its own — most often because the orchestrator is hoping for a
price/in-stock signal that this site fundamentally doesn't publish.

## What TFTCentral actually is

TFTCentral is a long-form monitor **review** site, not a retailer:

- Every product page lives under `/reviews/<brand>-<model-slug>`.
- There is no checkout, no cart, no configured price, no SKU.
- Affiliate links scattered through the article body usually point
  at *recommended alternatives*, not the reviewed model itself.
- The body is 10k+ words — don't try to read it; the meta tags
  and JSON-LD at the top of `<head>` carry everything you need.

If the spec requires a price or in-stock check, **do not try to
extract one from this page.** Return what's available (title,
brand, model, image, description) and let the orchestrator route
to a real retailer (Amazon, Newegg, Overclockers, Scan) for the
transactional fields.

## Selectors that work

- Product title: `h1.cm-entry-title` (leading whitespace is common —
  strip it). Format is consistent: `"<Brand> <Model>"`.
- Hero image: `meta[property="og:image"]` — always the
  `wp-content/uploads/.../banner.jpg` asset.
- One-line summary: `meta[name="description"]` (HTML-encoded — run
  it through `html.unescape`; the 32" in "32&quot; WOLED" decodes
  to a literal double-quote, which is what we want).
- JSON-LD fallback: `script.yoast-schema-graph` with `@graph[]`
  containing an `@type: "Article"` node. `headline` is the bare
  product name; `description` matches the meta description.

## Title → brand/model split

The H1 is always `"<Brand> <Model>"`. Known monitor brands include
LG, Samsung, ASUS, MSI, Dell, Alienware, AOC, Acer, BenQ, Philips,
ViewSonic, Gigabyte, Cooler Master, Innocn, KTC, NZXT, iiyama.
For multi-word brands (Cooler Master) consume two tokens before the
model code. Model codes are short alphanumerics ("32GS95UE",
"AW3225QF", "U28G2XU") — uppercase them.

## What the spec.must_haves can tell you

Reviewers consistently call out these specs in the first paragraph
and the `<h2>` headings. If the spec needs to match:

- Panel tech: search for "WOLED", "QD-OLED", "OLED", "IPS", "VA",
  "TN" in the first 2k chars of body text.
- Resolution: "4K", "1440p", "1080p", "UHD", "QHD", "5120x1440".
- Refresh rate: numbers immediately followed by "Hz" near the top.
- Size: `\d+(\.\d+)?["″]` (e.g. `31.5"`, `27″`). Note both ASCII
  `"` and Unicode `″` (PRIME) appear; normalise to ASCII.
- Dual-mode: phrase "dual mode" or "dual-mode" plus a second Hz
  number ("1080p at 480Hz").

## Pitfalls

- The page contains affiliate links to *other* products via
  `click.linksynergy.com` redirects. These are NOT prices for the
  reviewed model — never report one as the listing price.
- A cookie banner (Complianz) appears on first load; it doesn't
  block the static HTML, so don't waste a click on it unless you're
  about to interact with the page.
- `og:type` is `article` (not `product`) and there is no
  `Product` JSON-LD — don't waste a parse pass looking for one.
- The `<title>` tag is `"<Product> Review - TFTCentral"`. Strip the
  `" Review - TFTCentral"` suffix when falling back to it.
- The article body wraps the product name in `&#8243;` (″) and
  `&#8217;` (') HTML entities — always unescape.
- No captcha, no geo gating, no login wall. If a page returns 404
  the slug is wrong; check capitalisation of the model code.
