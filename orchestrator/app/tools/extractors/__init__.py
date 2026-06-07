# Deterministic per-domain extractors. Modules in this package follow the
# ``async def extract(page: Page, spec: dict) -> dict`` contract; the
# matching ``<domain>.md`` files hold prompt hints injected into the
# browser-agent fallback's system prompt.
