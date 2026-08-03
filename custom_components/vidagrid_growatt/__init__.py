"""The VidaGrid Growatt (Base Power batteries) integration."""

from __future__ import annotations

import secrets

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import webhook as vidagrid_webhook
from .api import VidaGridApiClient, VidaGridApiError, VidaGridAuthError
from .const import CONF_BASE_URL, CONF_BEARER_TOKEN, CONF_INVERTER_SNS, CONF_WEBHOOK_ID, DOMAIN
from .coordinator import VidaGridCoordinator

PLATFORMS = ["sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = VidaGridApiClient(session, entry.data[CONF_BASE_URL], entry.data[CONF_BEARER_TOKEN])
    inverter_sns = [s.strip() for s in entry.data[CONF_INVERTER_SNS].split(",") if s.strip()]

    coordinator = VidaGridCoordinator(hass, api, inverter_sns)

    try:
        await coordinator.async_config_entry_first_refresh()
    except (VidaGridAuthError, VidaGridApiError) as err:
        raise ConfigEntryNotReady(str(err)) from err

    # Generate a stable webhook_id once per entry (persisted so it survives
    # reloads/restarts) for the browser userscript to push fresh data to.
    if CONF_WEBHOOK_ID not in entry.data:
        webhook_id = secrets.token_hex(16)
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_WEBHOOK_ID: webhook_id}
        )
    else:
        webhook_id = entry.data[CONF_WEBHOOK_ID]

    vidagrid_webhook.register(hass, webhook_id, coordinator)

    persistent_notification.async_create(
        hass,
        (
            f"Webhook path for the browser relay script:\n\n"
            f"`/api/webhook/{webhook_id}`\n\n"
            f"Full URL (replace the host if this isn't your Home Assistant "
            f"address): `http://YOUR-HA-ADDRESS:8123/api/webhook/{webhook_id}`\n\n"
            f"See this integration's README.md for how to use it."
        ),
        title="VidaGrid Growatt: webhook ready",
        notification_id=f"vidagrid_growatt_webhook_{entry.entry_id}",
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    entry.async_on_unload(lambda: vidagrid_webhook.unregister(hass, webhook_id))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
