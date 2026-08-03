"""The VidaGrid Growatt (Base Power batteries) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VidaGridApiClient, VidaGridApiError, VidaGridAuthError
from .const import CONF_BASE_URL, CONF_BEARER_TOKEN, CONF_INVERTER_SNS, DOMAIN
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

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
