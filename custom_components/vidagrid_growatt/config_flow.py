"""Config flow for the VidaGrid Growatt integration.

The portal's login page requires solving a CAPTCHA, so this integration
cannot authenticate on its own. The user signs into the portal normally in
their browser, copies the Bearer token their browser already holds, and
pastes it here. See README.md (packaged alongside this integration) for the
exact dev-tools steps to grab that token.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VidaGridApiClient, VidaGridAuthError, VidaGridApiError
from .const import (
    CONF_BASE_URL,
    CONF_BEARER_TOKEN,
    CONF_INVERTER_SNS,
    CONF_SITE_ID,
    DEFAULT_BASE_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _parse_sns(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


async def _validate(hass: HomeAssistant, data: dict[str, Any]) -> None:
    session = async_get_clientsession(hass)
    api = VidaGridApiClient(session, data[CONF_BASE_URL], data[CONF_BEARER_TOKEN])
    sns = _parse_sns(data[CONF_INVERTER_SNS])
    if not sns:
        raise ValueError("no_inverters")
    await api.async_validate_token(sns[0])


class VidaGridConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup and re-authentication for VidaGrid Growatt."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _validate(self.hass, user_input)
            except VidaGridAuthError:
                errors["base"] = "invalid_auth"
            except VidaGridApiError:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "no_inverters"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating VidaGrid token")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_SITE_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"VidaGrid Site {user_input[CONF_SITE_ID]}",
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_BEARER_TOKEN): str,
                vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
                vol.Required(CONF_SITE_ID): str,
                vol.Required(CONF_INVERTER_SNS): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "token_help": (
                    "Sign into growatt-us.vidagrid.com in your browser, open dev "
                    "tools > Network, reload, click any /web/v1/ request, and "
                    "copy the value after 'Bearer ' in its Authorization header."
                )
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None

        if user_input is not None:
            new_data = {**self._reauth_entry.data, CONF_BEARER_TOKEN: user_input[CONF_BEARER_TOKEN]}
            try:
                await _validate(self.hass, new_data)
            except VidaGridAuthError:
                errors["base"] = "invalid_auth"
            except VidaGridApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating VidaGrid token during reauth")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(self._reauth_entry, data=new_data)
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_BEARER_TOKEN): str}),
            errors=errors,
        )
