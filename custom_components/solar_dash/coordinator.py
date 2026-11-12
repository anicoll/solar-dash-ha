"""Data update coordinators: live readings, today's totals and prices."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    SolarDashAuthError,
    SolarDashClient,
    SolarDashConnectionError,
)
from .const import LOGGER, PRICES_INTERVAL, TODAY_INTERVAL


class _SolarDashCoordinator[T](DataUpdateCoordinator[T]):
    """Shared error handling: 401 means reauth, anything else a failed update."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SolarDashClient,
        name: str,
        interval: timedelta,
    ) -> None:
        super().__init__(
            hass, LOGGER, config_entry=entry, name=name, update_interval=interval
        )
        self.client = client

    async def _async_update_data(self) -> T:
        try:
            return await self._fetch()
        except SolarDashAuthError as err:
            raise ConfigEntryAuthFailed("solar-dash rejected the API token") from err
        except SolarDashConnectionError as err:
            raise UpdateFailed(f"Error talking to solar-dash: {err}") from err

    async def _fetch(self) -> T:
        raise NotImplementedError


class LiveCoordinator(_SolarDashCoordinator[dict[str, Any]]):
    """`/api/live`: the newest inverter sample, `{}` when there is none."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SolarDashClient,
        interval: timedelta,
    ) -> None:
        super().__init__(hass, entry, client, "solar-dash live", interval)

    async def _fetch(self) -> dict[str, Any]:
        payload = await self.client.live()
        # `sample` is null when Modbus is off or the sample is too old to be live.
        return payload.get("sample") or {}


@dataclass
class TodayData:
    """Today's totals for the local day `date`."""

    date: str
    # `/api/daily` row (pv_kwh, load_kwh, import_kwh, ...): None = no data yet.
    energy: dict[str, Any] = field(default_factory=dict)
    # `/api/costs` row for the day, or None without a tariff or data.
    cost: dict[str, Any] | None = None

    @property
    def power_cost(self) -> float | None:
        """Bought less sold, in dollars (negative when selling earned more)."""
        if self.cost is None:
            return None
        return round(self.cost["import"] - self.cost["feed_in"], 2)

    @property
    def net_cost(self) -> float | None:
        """Supply charge and bought, less sold and credits: `actual` in `/api/costs`."""
        return None if self.cost is None else self.cost["actual"]


class TodayCoordinator(_SolarDashCoordinator[TodayData]):
    """Today's energy (`/api/daily`) and cost (`/api/costs`)."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SolarDashClient,
        has_costs: bool,
    ) -> None:
        super().__init__(hass, entry, client, "solar-dash today", TODAY_INTERVAL)
        self._has_costs = has_costs

    async def _fetch(self) -> TodayData:
        # "Today" is Home Assistant's local date; solar-dash is assumed to be
        # in the same time zone (the usual home setup).
        today = dt_util.now().date()
        daily = await self.client.daily(today)
        days = daily.get("days") or []
        row = next((d for d in days if d.get("date") == today.isoformat()), None)
        data = TodayData(date=today.isoformat(), energy=row or {})
        if self._has_costs:
            costs = await self.client.costs(today)
            if costs.get("configured"):
                data.cost = next(
                    (
                        d
                        for d in costs.get("days") or []
                        if d.get("date") == today.isoformat()
                    ),
                    None,
                )
        return data


@dataclass
class PricesData:
    """Amber's prices right now, in c/kWh."""

    general: float | None
    # What you earn: Amber's raw feed-in price is negative when you are paid,
    # so it is flipped here, like solar-dash's UI and its MQTT feed do.
    feed_in: float | None
    descriptor: str | None


class PricesCoordinator(_SolarDashCoordinator[PricesData]):
    """`/api/prices` `now` block."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: SolarDashClient
    ) -> None:
        super().__init__(hass, entry, client, "solar-dash prices", PRICES_INTERVAL)

    async def _fetch(self) -> PricesData:
        payload = await self.client.prices_now(int(time.time()))
        now = payload.get("now") or {}
        general = now.get("general") or {}
        feed_in = now.get("feed_in") or {}
        raw_feed_in = feed_in.get("cents")
        general_cents = general.get("cents")
        return PricesData(
            general=None if general_cents is None else round(general_cents, 1),
            # `0.0 - x` instead of `-x` so a raw 0 gives 0, not -0.
            feed_in=None if raw_feed_in is None else round(0.0 - raw_feed_in, 1),
            descriptor=general.get("descriptor"),
        )
