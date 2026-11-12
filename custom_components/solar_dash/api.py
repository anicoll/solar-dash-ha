"""Small async client for solar-dash's HTTP API.

solar-dash accepts ``Authorization: Bearer <api_token>`` on GET routes under
``/api/``. Nothing here ever writes: the token is read-only on the server too.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import aiohttp

from .const import REQUEST_TIMEOUT


class SolarDashError(Exception):
    """Base class for client errors."""


class SolarDashConnectionError(SolarDashError):
    """The server could not be reached, timed out or answered badly."""


class SolarDashAuthError(SolarDashError):
    """The server rejected the API token (HTTP 401)."""


class SolarDashClient:
    """Reads solar-dash's JSON API."""

    def __init__(
        self, session: aiohttp.ClientSession, base_url: str, token: str
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._token = token

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET `path` and return the decoded JSON."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.get(
                    f"{self._base_url}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                if response.status in (401, 403):
                    raise SolarDashAuthError(f"HTTP {response.status} from {path}")
                response.raise_for_status()
                return await response.json(content_type=None)
        except SolarDashAuthError:
            raise
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            raise SolarDashConnectionError(f"{path}: {err}") from err

    async def capabilities(self) -> dict[str, Any]:
        """`/api/capabilities`: which parts this install has."""
        return await self._get("/api/capabilities")

    async def live(self) -> dict[str, Any]:
        """`/api/live`: `{"sample": {...} | null, "car": ..., "grid_pull": ...}`."""
        return await self._get("/api/live")

    async def daily(self, day: date) -> dict[str, Any]:
        """`/api/daily` for one local day: `{"days": [{...}]}`."""
        return await self._get(
            "/api/daily", {"from": day.isoformat(), "to": day.isoformat()}
        )

    async def costs(self, day: date) -> dict[str, Any]:
        """`/api/costs` for one local day (`{"configured": false}` without a tariff)."""
        return await self._get(
            "/api/costs",
            {"from": day.isoformat(), "to": day.isoformat(), "group": "day"},
        )

    async def prices_now(self, now: int) -> dict[str, Any]:
        """`/api/prices`; only its `now` block is used."""
        return await self._get("/api/prices", {"from": now, "to": now})
