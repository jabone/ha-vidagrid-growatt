"""Data coordinator for the VidaGrid Growatt integration.

Two data paths feed this coordinator:

1. A slow fallback poll (`_async_update_data`, every
   DEFAULT_SCAN_INTERVAL_SECONDS) using the pasted bearer token. Given the
   token has been observed expiring in as little as ~15-25 minutes, this
   path is expected to fail routinely and is treated as best-effort: a
   failed fetch just keeps the last-known-good value per inverter/section
   rather than erroring the whole entity set to unavailable or forcing a
   re-auth prompt every time.
2. A webhook push (`ingest()`, called from webhook.py) fed by a userscript
   running in the user's own already-authenticated browser tab. This is
   the primary, frequent, sustainable path -- see README.md.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import (
    VidaGridApiClient,
    VidaGridApiError,
    VidaGridAuthError,
    parse_battery_raw,
    parse_diagram_raw,
)
from .const import DEFAULT_SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class VidaGridCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Hold battery + diagram data for every configured inverter.

    Populated by a best-effort fallback poll and/or webhook pushes; never
    raises out of `_async_update_data` after the very first successful
    refresh, so a dead/expired pasted token doesn't flip every entity to
    unavailable -- they just hold their last real reading, same as the
    Base Power integration's own last-known-good caching fix.
    """

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
        self._cache: dict[str, dict[str, Any]] = {
            sn: {"battery": None, "diagram": None} for sn in inverter_sns
        }
        self._ever_succeeded = False

    async def _async_update_data(self) -> dict[str, Any]:
        any_success = False
        last_error: Exception | None = None

        for sn in self.inverter_sns:
            try:
                self._cache.setdefault(sn, {"battery": None, "diagram": None})
                self._cache[sn]["battery"] = await self.api.async_get_battery(sn)
                any_success = True
            except (VidaGridAuthError, VidaGridApiError) as err:
                _LOGGER.debug("Fallback battery poll failed for %s: %s", sn, err)
                last_error = err

            try:
                self._cache[sn]["diagram"] = await self.api.async_get_diagram(sn)
                any_success = True
            except (VidaGridAuthError, VidaGridApiError) as err:
                _LOGGER.debug("Fallback diagram poll failed for %s: %s", sn, err)
                last_error = err

        if any_success:
            self._ever_succeeded = True
        elif not self._ever_succeeded:
            # Only the very first refresh can still fail loudly (surfaces as
            # ConfigEntryNotReady in __init__.py) -- after that, webhook
            # pushes or a later successful poll are enough to keep going.
            _LOGGER.warning(
                "VidaGrid fallback poll has never succeeded yet (%s); "
                "waiting for a webhook push or a valid token.",
                last_error,
            )

        return self._cache

    def ingest(
        self,
        sn: str,
        battery_raw: dict[str, Any] | None = None,
        diagram_raw: dict[str, Any] | None = None,
    ) -> None:
        """Merge a webhook-pushed raw payload into the cache and notify entities."""
        self._cache.setdefault(sn, {"battery": None, "diagram": None})
        if battery_raw is not None:
            self._cache[sn]["battery"] = parse_battery_raw(battery_raw)
        if diagram_raw is not None:
            self._cache[sn]["diagram"] = parse_diagram_raw(diagram_raw)
        self._ever_succeeded = True
        self.async_set_updated_data(self._cache)
