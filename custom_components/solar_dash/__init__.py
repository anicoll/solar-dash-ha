"""The solar-dash integration: polls solar-dash's HTTP API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SolarDashAuthError, SolarDashClient, SolarDashConnectionError
from .const import CONF_API_TOKEN, CONF_SCAN_INTERVAL, CONF_URL, DEFAULT_SCAN_INTERVAL
from .coordinator import LiveCoordinator, PricesCoordinator, TodayCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


@dataclass
class SolarDashData:
    """Everything a config entry keeps at runtime."""

    client: SolarDashClient
    capabilities: dict[str, Any]
    live: LiveCoordinator
    today: TodayCoordinator
    # Only when solar-dash has a price source (`capabilities["prices"]`).
    prices: PricesCoordinator | None


type SolarDashConfigEntry = ConfigEntry[SolarDashData]


async def async_setup_entry(hass: HomeAssistant, entry: SolarDashConfigEntry) -> bool:
    """Set up solar-dash from a config entry."""
    client = SolarDashClient(
        async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_API_TOKEN]
    )
    try:
        capabilities = await client.capabilities()
    except SolarDashAuthError as err:
        raise ConfigEntryAuthFailed("solar-dash rejected the API token") from err
    except SolarDashConnectionError as err:
        raise ConfigEntryNotReady(f"Cannot reach solar-dash: {err}") from err

    interval = timedelta(
        seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    live = LiveCoordinator(hass, entry, client, interval)
    today = TodayCoordinator(hass, entry, client, bool(capabilities.get("costs")))
    prices = (
        PricesCoordinator(hass, entry, client) if capabilities.get("prices") else None
    )
    coordinators = [c for c in (live, today, prices) if c is not None]
    for coordinator in coordinators:
        await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = SolarDashData(client, capabilities, live, today, prices)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Reload when the options (scan interval) change.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: SolarDashConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SolarDashConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
