"""Sensor values, capability gating, reauth and diagnostics."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import TOKEN, URL, mock_api


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, entry: MockConfigEntry, key: str):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", "solar_dash", f"{entry.entry_id}_{key}"
    )
    assert entity_id, f"no entity for {key}"
    return hass.states.get(entity_id)


async def test_all_sensor_values(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    mock_api(aioclient_mock)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    expected = {
        # /api/live sample: pv_w, load_w, grid_w (-1800 = exporting), battery_w
        "solar_power": "4200.4",
        "home_load": "1500.0",
        "grid_power": "-1800.0",
        "battery_power": "900.0",
        "battery_soc": "63.5",
        "grid_import": "0.0",
        "grid_export": "1800.0",
        # /api/daily row
        "today_grid_import": "3.1",
        "today_grid_export": "7.6",
        "today_solar": "18.4",
        "today_battery_charge": "5.2",
        "today_battery_discharge": "4.1",
        "today_home_use": "12.25",
        # /api/costs row: power = import - feed_in, net = actual
        "today_power_cost": "0.85",
        "today_net_cost": "1.9",
        # /api/prices now
        "amber_general_price": "28.4",
        "amber_feed_in_price": "8.3",
        "amber_descriptor": "neutral",
    }
    for key, value in expected.items():
        assert _state(hass, entry, key).state == value, key


async def test_power_cost_is_import_minus_feed_in(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    mock_api(aioclient_mock)
    await _setup(hass, entry)
    # import 1.20 - feed_in 0.35; net is `actual` (includes the 1.05 supply charge).
    assert entry.runtime_data.today.data.power_cost == 0.85
    assert entry.runtime_data.today.data.net_cost == 1.9


async def test_importing_signs(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    mock_api(aioclient_mock, live="live_importing")
    await _setup(hass, entry)
    assert _state(hass, entry, "grid_power").state == "1200.0"
    assert _state(hass, entry, "grid_import").state == "1200.0"
    assert _state(hass, entry, "grid_export").state == "0.0"
    assert _state(hass, entry, "battery_power").state == "-1300.0"


async def test_feed_in_price_is_flipped_to_earned(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    mock_api(aioclient_mock)
    await _setup(hass, entry)
    # Raw feed-in is -8.26 c/kWh (customer is paid): shown as +8.3 earned.
    assert _state(hass, entry, "amber_feed_in_price").state == "8.3"
    prices = entry.runtime_data.prices
    assert prices is not None and prices.data.feed_in == 8.3


async def test_energy_sensor_classes(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    mock_api(aioclient_mock)
    await _setup(hass, entry)
    state = _state(hass, entry, "today_solar")
    assert state.attributes["device_class"] == "energy"
    assert state.attributes["state_class"] == "total_increasing"
    assert state.attributes["unit_of_measurement"] == "kWh"
    assert (
        _state(hass, entry, "today_net_cost").attributes["unit_of_measurement"] == "AUD"
    )


async def test_missing_capabilities_create_no_entities(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    mock_api(aioclient_mock, capabilities="capabilities_minimal")
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.prices is None
    registry = er.async_get(hass)
    assert er.async_entries_for_config_entry(registry, entry.entry_id) == []


async def test_no_prices_or_costs_without_those_capabilities(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    caps = {"live": True, "history": False, "prices": False, "costs": False}
    aioclient_mock.get(f"{URL}/api/capabilities", json=caps)
    aioclient_mock.get(f"{URL}/api/live", json={"sample": None, "car": None})
    aioclient_mock.get(f"{URL}/api/daily", json={"days": []})
    await _setup(hass, entry)
    registry = er.async_get(hass)
    keys = {
        e.unique_id.removeprefix(f"{entry.entry_id}_")
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert "solar_power" in keys and "today_solar" in keys
    assert not keys & {"today_power_cost", "amber_general_price"}
    # A null sample (Modbus off or stale) gives unknown, not zero.
    assert _state(hass, entry, "solar_power").state == "unknown"
    called = {str(call[1].path) for call in aioclient_mock.mock_calls}
    assert "/api/costs" not in called and "/api/prices" not in called


async def test_401_on_setup_starts_reauth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    aioclient_mock.get(f"{URL}/api/capabilities", status=401)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler("solar_dash")
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_401_during_update_starts_reauth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    mock_api(aioclient_mock)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/live", status=401)
    await entry.runtime_data.live.async_refresh()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler("solar_dash")
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_timeout_during_update_is_update_failed(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    mock_api(aioclient_mock)
    await _setup(hass, entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/live", exc=TimeoutError)
    await entry.runtime_data.live.async_refresh()
    await hass.async_block_till_done()
    assert entry.runtime_data.live.last_update_success is False
    assert _state(hass, entry, "solar_power").state == "unavailable"
    assert not hass.config_entries.flow.async_progress_by_handler("solar_dash")


async def test_setup_not_ready_when_unreachable(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    aioclient_mock.get(f"{URL}/api/capabilities", exc=TimeoutError)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    mock_api(aioclient_mock)
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics_redacts_token(
    hass: HomeAssistant,
    hass_client,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    mock_api(aioclient_mock)
    await _setup(hass, entry)
    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    assert diagnostics["entry"]["api_token"] == "**REDACTED**"
    assert TOKEN not in str(diagnostics)
    assert diagnostics["capabilities"]["prices"] is True
