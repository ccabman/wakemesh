"""Async client for the WakeMesh app API."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientSession


class RouterApiError(Exception):
    """Raised when the router API cannot be queried."""


class RouterApiClient:
    """Minimal client used during the read-only API milestone."""

    def __init__(self, session: ClientSession, base_url: str, token: str) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def _get(self, path: str) -> dict[str, Any]:
        try:
            async with self._session.get(
                f"{self._base_url}{path}", headers=self._headers, timeout=10
            ) as response:
                response.raise_for_status()
                return await response.json()
        except (ClientError, TimeoutError, ValueError) as err:
            raise RouterApiError(str(err)) from err

    async def health(self) -> dict[str, Any]:
        return await self._get("/v1/health")

    async def status(self) -> dict[str, Any]:
        return await self._get("/v1/status")

