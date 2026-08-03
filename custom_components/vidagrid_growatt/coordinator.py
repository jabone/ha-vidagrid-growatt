"""Data coordinator for the VidaGrid Growatt integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VidaGridApiClient, VidaGridApiError, VidaGridAuthError
from .const import DEFAULT_SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class VidaGridCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll battery + diagram data for every configured inverter."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: VidaGridApiClient,
        inverter_sns: list[str],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="VidaGrid Growatt",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.api = api
        self.inverter_sns = inverter_sns

    async def _async_update_data(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        auth_failed = False
        last_error: Exception | None = None

        for sn in self.inverter_sns:
            inverter_data: dict[str, Any] = {"battery": None, "diagram": None}
            try:
                inverter_data["battery"] = await self.api.async_get_battery(sn)
            except VidaGridAuthError as err:
                auth_failed = True
                last_error = err
            except VidaGridApiError as err:
                _LOGGER.debug("Battery fetch failed for %s: %s", sn, err)
                last_error = err

            try:
                inverter_data["diagram"] = await self.api.async_get_diagram(sn)
            except VidaGridAuthError as err:
                auth_failed = True
                last_error = err
            except VidaGridApiError as err:
                _LOGGER.debug("Diagram fetch failed for %s: %s", sn, err)
                last_error = err

            result[sn] = inverter_data

        if auth_failed:
            raise ConfigEntryAuthFailed(
                "VidaGrid bearer token was rejected -- paste a fresh one from your browser"
            ) from last_error

        if all(v["battery"] is None and v["diagram"] is None for v in result.values()):
            raise UpdateFailed(f"Could not reach VidaGrid API: {last_error}")

        return result
