import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings
from app.db.client import InsforgeClient, InsforgeError

log = logging.getLogger(__name__)


async def _handle_intent(intent: dict) -> None:
    # TODO(h4-h7): hand off to intake / search-planner / researcher pipeline
    log.info("intent picked up: id=%s spec_keys=%s", intent.get("id"), list((intent.get("spec") or {}).keys()))


async def intent_poller_task() -> None:
    """Polls Insforge for ready intents and dispatches them.

    Insforge does not expose direct Postgres access, so we cannot LISTEN/NOTIFY.
    We mark each intent with picked_up_at to claim it; the WHERE clause filters
    those out so concurrent pollers (if any) don't double-process.
    """
    try:
        client = InsforgeClient()
    except InsforgeError as e:
        log.warning("poller disabled: %s", e)
        return

    backoff = 1.0
    while True:
        try:
            rows = await client.select(
                "intents",
                {
                    "status": "eq.ready",
                    "picked_up_at": "is.null",
                    "order": "created_at.asc",
                    "limit": "5",
                },
            )
            for row in rows:
                claimed = await client.update(
                    "intents",
                    where={"id": f"eq.{row['id']}", "picked_up_at": "is.null"},
                    patch={
                        "status": "researching",
                        "picked_up_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                if not claimed:
                    continue  # another worker beat us; skip
                asyncio.create_task(_handle_intent(claimed[0]))
            backoff = 1.0
        except asyncio.CancelledError:
            await client.close()
            raise
        except Exception as e:
            log.error("poll error: %s; retry in %.1fs", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue

        await asyncio.sleep(settings.poll_interval_seconds)
