"""Diagnostics for solar-dash (the API token and URL are redacted)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import SolarDashConfigEntry
from .const import CONF_API_TOKEN, CONF_URL

TO_REDACT = {CONF_API_TOKEN, CONF_URL}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SolarDashConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "capabilities": data.capabilities,
        "live": data.live.data,
        "today": asdict(data.today.data) if data.today.data else None,
        "prices": asdict(data.prices.data)
        if data.prices and data.prices.data
        else None,
    }
