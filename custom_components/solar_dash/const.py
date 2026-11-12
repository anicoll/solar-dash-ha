"""Constants for the solar-dash integration."""

from __future__ import annotations

import logging
from datetime import timedelta

DOMAIN = "solar_dash"
LOGGER = logging.getLogger(__package__)

CONF_URL = "url"
CONF_API_TOKEN = "api_token"
CONF_SCAN_INTERVAL = "scan_interval"

# Live readings: solar-dash samples the inverter about every 15 s.
DEFAULT_SCAN_INTERVAL = 15
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300

# Today's totals and the Amber prices change slowly (same cadence as the MQTT feed).
TODAY_INTERVAL = timedelta(seconds=60)
PRICES_INTERVAL = timedelta(seconds=60)

REQUEST_TIMEOUT = 10  # seconds
