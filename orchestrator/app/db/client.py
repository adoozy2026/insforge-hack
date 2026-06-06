from typing import Any

import httpx

from app.config import settings


class InsforgeError(RuntimeError):
    pass


class InsforgeClient:
    """Minimal async REST client for Insforge's records API.

    Uses the service role key so the orchestrator can read/write any table
    regardless of RLS policies. Never expose this client to the browser.
    """

    def __init__(self) -> None:
        if not settings.insforge_project_url:
            raise InsforgeError("INSFORGE_PROJECT_URL not set")
        if not settings.insforge_service_role_key:
            raise InsforgeError("INSFORGE_SERVICE_ROLE_KEY not set")
        self._http = httpx.AsyncClient(
            base_url=settings.insforge_project_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {settings.insforge_service_role_key}",
                "Content-Type": "application/json",
            },
            timeout=20.0,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def select(self, table: str, query: dict[str, str] | None = None) -> list[dict[str, Any]]:
        r = await self._http.get(f"/api/database/records/{table}", params=query or {})
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else [data]

    async def insert(self, table: str, row: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload = row if isinstance(row, list) else [row]
        r = await self._http.post(
            f"/api/database/records/{table}",
            json=payload,
            headers={"Prefer": "return=representation"},
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else [data]

    async def update(self, table: str, where: dict[str, str], patch: dict[str, Any]) -> list[dict[str, Any]]:
        r = await self._http.patch(
            f"/api/database/records/{table}",
            params=where,
            json=patch,
            headers={"Prefer": "return=representation"},
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else [data]
