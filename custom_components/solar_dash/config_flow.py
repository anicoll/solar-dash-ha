"""Config flow: URL + API token, reauth and the options flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from yarl import URL

from .api import SolarDashAuthError, SolarDashClient, SolarDashConnectionError
from .const import (
    CONF_API_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def normalize_url(raw: str) -> URL | None:
    """Parse the typed address. A bare `192.168.1.5:8080` gets `http://`."""
    text = raw.strip().rstrip("/")
    if "://" not in text:
        text = f"http://{text}"
    try:
        url = URL(text)
    except ValueError:
        return None
    if url.scheme not in ("http", "https") or not url.host:
        return None
    return url


class SolarDashConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up solar-dash."""

    VERSION = 1

    async def _check(self, url: str, token: str) -> str | None:
        """Call `/api/capabilities` with the token; return an error key or None."""
        client = SolarDashClient(async_get_clientsession(self.hass), url, token)
        try:
            await client.capabilities()
        except SolarDashAuthError:
            return "invalid_auth"
        except SolarDashConnectionError:
            return "cannot_connect"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = normalize_url(user_input[CONF_URL])
            if url is None:
                errors[CONF_URL] = "invalid_url"
            else:
                await self.async_set_unique_id(url.host)
                self._abort_if_unique_id_configured()
                token = user_input[CONF_API_TOKEN].strip()
                if error := await self._check(str(url), token):
                    errors["base"] = error
                else:
                    return self.async_create_entry(
                        title=f"solar-dash ({url.host})",
                        data={CONF_URL: str(url).rstrip("/"), CONF_API_TOKEN: token},
                    )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_URL,
                    default=(user_input or {}).get(CONF_URL, "http://"),
                ): str,
                vol.Required(CONF_API_TOKEN): _TOKEN_SELECTOR,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            token = user_input[CONF_API_TOKEN].strip()
            if error := await self._check(entry.data[CONF_URL], token):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_TOKEN: token}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_TOKEN): _TOKEN_SELECTOR}),
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SolarDashOptionsFlow()


class SolarDashOptionsFlow(OptionsFlow):
    """Options: how often the live readings are polled."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
