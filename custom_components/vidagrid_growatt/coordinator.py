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
   the primary, frequent, sustainable path for battery, diagram, AND
   power_curve data -- see README.md and vidagrid_relay/README.md. As of
   the userscript's v1.1.0, this is the only path power_curve needs; the
   fallback poll's own power_curve fetch (below) is now just a secondary
   safety net rather than power_curve's sole source.
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
    parse_power_curve_raw,
)
from .const import DEFAULT_SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class VidaGridCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Hold battery + diagram + power_curve data for every configured inverter.

    Populated by a best-effort fallback poll and/or webhook pushes; never
    raises out of _async_update_data after the very first successful
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
            sn: {"battery": None, "diagram": None, "power_curve": None} for sn in inverter_sns
        }
        self._ever_succeeded = False
        # Entities register themselves here (see sensor.py / binary_sensor.py)
        # so ingest() can write their state directly, in addition to the
        # normal coordinator listener notification. This is a defensive
        # belt-and-suspenders measure: on 2026.8 beta core builds we observed
        # async_set_updated_data()/async_update_listeners() silently stop
        # producing entity state writes after a couple of cycles, even
        # though the coordinator and its listener count looked completely
        # healthy (see custom_components/vidagrid_growatt/webhook.py logging
        # and the project README for the full writeup). Direct writes here
        # don't depend on that listener-dispatch path at all, so entities
        # stay live regardless of whether that turns out to be an upstream
        # core bug.
        self.entities_by_sn: dict[str, list[Any]] = {sn: [] for sn in inverter_sns}

    def register_entity(self, sn: str, entity: Any) -> None:
        """Track an entity so ingest() can write its state directly."""
        self.entities_by_sn.setdefault(sn, []).append(entity)

    async def _async_update_data(self) -> dict[str, Any]:
        any_success = False
        last_error: Exception | None = None

        for sn in self.inverter_sns:
            try:
                self._cache.setdefault(sn, {"battery": None, "diagram": None, "power_curve": None})
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

            try:
                self._cache[sn]["power_curve"] = await self.api.async_get_power_curve(sn)
                any_success = True
            except (VidaGridAuthError, VidaGridApiError) as err:
                _LOGGER.debug("Fallback power curve poll failed for %s: %s", sn, err)
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
        power_curve_raw: dict[str, Any] | None = None,
    ) -> None:
        """Merge a webhook-pushed raw payload into the cache and notify entities."""
        self._cache.setdefault(sn, {"battery": None, "diagram": None, "power_curve": None})
        if battery_raw is not None:
            self._cache[sn]["battery"] = parse_battery_raw(battery_raw)
        if diagram_raw is not None:
            self._cache[sn]["diagram"] = parse_diagram_raw(diagram_raw)
        if power_curve_raw is not None:
            self._cache[sn]["power_curve"] = parse_power_curve_raw(power_curve_raw)
        self._ever_succeeded = True

        # Normal path: updates .data, reschedules the fallback poll timer,
        # and notifies every registered coordinator listener.
        self.async_set_updated_data(self._cache)

        # Belt-and-suspenders path: also write the affected entities'
        # state directly, bypassing the listener-notification mechanism
        # entirely. See the comment in __init__ for why.
        direct_written = 0
        for entity in self.entities_by_sn.get(sn, []):
            if getattr(entity, "hass", None) is not None:
                entity.async_write_ha_state()
                direct_written += 1
        _LOGGER.debug(
            "ingest(%s): notified via coordinator listeners, and directly "
            "wrote %d/%d registered entities",
            sn,
            direct_written,
            len(self.entities_by_sn.get(sn, [])),
        )
