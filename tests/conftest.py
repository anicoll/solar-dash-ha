"""Shared fixtures."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.solar_dash.const import CONF_API_TOKEN, CONF_URL, DOMAIN

URL = "http://192.168.1.20:8080"
TOKEN = "0123456789abcdef0123456789abcdef0123456789abcdef"
TODAY = "2026-11-12"

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load custom_components/solar_dash."""


@pytest.fixture(autouse=True)
def fixed_today() -> Generator[None]:
    """Pin "today" to the date inside the fixtures."""
    from datetime import date

    with patch("custom_components.solar_dash.coordinator.dt_util.now") as now:
        now.return_value.date.return_value = date.fromisoformat(TODAY)
        yield


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="solar-dash (192.168.1.20)",
        unique_id="192.168.1.20",
        data={CONF_URL: URL, CONF_API_TOKEN: TOKEN},
    )


def mock_api(
    mocker: AiohttpClientMocker,
    capabilities: str = "capabilities_full",
    live: str = "live",
) -> None:
    """Answer every route solar-dash serves, from the fixtures."""
    mocker.get(f"{URL}/api/capabilities", json=load(capabilities))
    mocker.get(f"{URL}/api/live", json=load(live))
    mocker.get(f"{URL}/api/daily", json=load("daily"))
    mocker.get(f"{URL}/api/costs", json=load("costs"))
    mocker.get(f"{URL}/api/prices", json=load("prices"))
