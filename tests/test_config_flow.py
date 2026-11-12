"""Config flow, reauth and options flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.solar_dash.const import (
    CONF_API_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    DOMAIN,
)

from .conftest import TOKEN, URL, load, mock_api


async def _start(hass: HomeAssistant, url: str = URL, token: str = TOKEN):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: url, CONF_API_TOKEN: token}
    )


async def test_user_flow_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_api(aioclient_mock)
    result = await _start(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_URL: URL, CONF_API_TOKEN: TOKEN}
    assert result["result"].unique_id == "192.168.1.20"
    # The token was sent as a bearer on the capabilities call.
    method, url, _data, headers = aioclient_mock.mock_calls[0]
    assert str(url).endswith("/api/capabilities")
    assert headers["Authorization"] == f"Bearer {TOKEN}"


async def test_user_flow_bare_host_gets_http(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_api(aioclient_mock)
    result = await _start(hass, "192.168.1.20:8080")
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_URL] == URL


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{URL}/api/capabilities", exc=TimeoutError)
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_invalid_auth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{URL}/api/capabilities", status=401)
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_invalid_url(hass: HomeAssistant) -> None:
    result = await _start(hass, "ftp://nope")
    assert result["errors"] == {CONF_URL: "invalid_url"}


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    entry.add_to_hass(hass)
    mock_api(aioclient_mock)
    result = await _start(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    entry.add_to_hass(hass)
    mock_api(aioclient_mock)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    new_token = "f" * 48
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: new_token}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_TOKEN] == new_token


async def test_reauth_flow_wrong_token(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    entry.add_to_hass(hass)
    aioclient_mock.get(f"{URL}/api/capabilities", status=401)
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}


async def test_options_flow(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
) -> None:
    mock_api(aioclient_mock)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL: 30}
    await hass.async_block_till_done()
    assert entry.runtime_data.live.update_interval.total_seconds() == 30
    assert load("capabilities_full")["live"]
