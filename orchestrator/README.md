# orchestrator

Local FastAPI service that runs the agent pipeline. Talks to Insforge Postgres outbound-only — woken by `pg_notify('intent_ready', ...)` from the UI inserting a row.

## Run locally

```bash
uv sync
cp ../.env.example ../.env   # fill in keys
uv run uvicorn app.main:app --reload --port 8787
```

Health check: `curl localhost:8787/healthz`
