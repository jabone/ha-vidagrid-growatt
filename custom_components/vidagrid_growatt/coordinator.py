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
   the primary, frequent, sustainable path for battery, diagram, power_curve,
   AND energy_curve data -- see README.md and vidagrid_relay/README.md. As
   of the userscript's v1.2.0, this is the only path the two curve
   endpoints need; the fallback poll's own curve fetches (below) are now
   just a secondary safety net rather than their sole source.

As of the relay's v1.3.0, the webhook push also carries the browser's
current bearer token and an explicit login-status flag (see
set_relay_logged_in() below), so this coordinator's own fallback-poll
client stays current automatically and the integration can surface a clear
"log back in" prompt when the relay's browser session has logged out --
instead of that path just silently going stale forever.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import (
    VidaGridApiClient,
    VidaGridApiError,
    VidaGridAuthError,
    parse_battery_raw,
    parse_diagram_raw,
    parse_energy_curve_raw,
    parse_power_curve_raw,
)
from .const import DEFAULT_SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

_EMPTY_CACHE_ENTRY = {
    "battery": None,
    "diagram": None,
    "power_curve": None,
    "energy_curve": None,
}

_RELAY_LOGGED_OUT_NOTIFICATION_ID = "vidagrid_growatt_relay_logged_out"


class VidaGridCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Hold battery/diagram/power_curve/energy_curve data for every configured inverter.

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
            sn: dict(_EMPTY_CACHE_ENTRY) for sn in inverter_sns
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

        # Account-level (not per-inverter) relay session status, reported by
        # the browser relay extension on every webhook push. `logged_in` is
        # None until the relay has checked in at least once.
        self.relay_status: dict[str, Any] = {"logged_in": None, "last_changed": None}
        self._relay_status_entities: list[Any] = []

    def register_entity(self, sn: str, entity: Any) -> None:
        """Track an entity so ingest() can write its state directly."""
        self.entities_by_sn.setdefault(sn, []).append(entity)

    def register_relay_status_entity(self, entity: Any) -> None:
        """Track an entity (e.g. the relay-session binary sensor) for direct writes."""
        self._relay_status_entities.append(entity)

    async def _async_update_data(self) -> dict[str, Any]:
        any_success = False
        last_error: Exception | None = None
        now = dt_util.now()

        for sn in self.inverter_sns:
            self._cache.setdefault(sn, dict(_EMPTY_CACHE_ENTRY))

            try:
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
                self._cache[sn]["power_curve"] = await self.api.async_get_power_curve(sn, now)
                any_success = True
            except (VidaGridAuthError, VidaGridApiError) as err:
                _LOGGER.debug("Fallback power curve poll failed for %s: %s", sn, err)
                last_error = err

            try:
                self._cache[sn]["energy_curve"] = await self.api.async_get_energy_curve(sn, now)
                any_success = True
            except (VidaGridAuthError, VidaGridApiError) as err:
                _LOGGER.debug("Fallback energy curve poll failed for %s: %s", sn, err)
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
        energy_curve_raw: dict[str, Any] | None = None,
    ) -> None:
        """Merge a webhook-pushed raw payload into the cache and notify entities."""
        self._cache.setdefault(sn, dict(_EMPTY_CACHE_ENTRY))
        if battery_raw is not None:
            self._cache[sn]["battery"] = parse_battery_raw(battery_raw)
        if diagram_raw is not None:
            self._cache[sn]["diagram"] = parse_diagram_raw(diagram_raw)
        if power_curve_raw is not None:
            self._cache[sn]["power_curve"] = parse_power_curve_raw(power_curve_raw)
        if energy_curve_raw is not None:
            self._cache[sn]["energy_curve"] = parse_energy_curve_raw(energy_curve_raw)
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

    def set_relay_logged_in(self, logged_in: bool) -> None:
        """Record the relay browser extension's current login status.

        Called from webhook.py on every push that includes a `logged_in`
        flag or a fresh `token`. Fires (and clears) a persistent notification
        on a True<->False transition so a logged-out relay surfaces as an
        actionable prompt -- open the add-on's Web UI and sign back in --
        rather than data just quietly going stale.
        """
        previous = self.relay_status.get("logged_in")
        self.relay_status["logged_in"] = logged_in
        self.relay_status["last_changed"] = dt_util.now().isoformat()

        if logged_in is False and previous is not False:
            persistent_notification.async_create(
                self.hass,
                (
                    "The VidaGrid Relay add-on's browser session has logged "
                    "out, so fresh battery/solar data has stopped flowing.\n\n"
                    "Open **Settings > Add-ons > VidaGrid Relay > Open Web "
                    "UI**, sign back into growatt-us.vidagrid.com (solving "
                    "the captcha), and check any \"stay signed in\" or "
                    "\"remember me\" option the portal offers so this "
                    "happens as rarely as possible -- the same tradeoff "
                    "apps like Nest or Apple Home ask you to make. Data "
                    "resumes automatically once you're logged back in; "
                    "nothing needs to change here in Home Assistant."
                ),
                title="VidaGrid Growatt: relay needs you to log back in",
                notification_id=_RELAY_LOGGED_OUT_NOTIFICATION_ID,
            )
        elif logged_in is True and previous is False:
            persistent_notification.async_dismiss(
                self.hass, _RELAY_LOGGED_OUT_NOTIFICATION_ID
            )

        self.async_update_listeners()
        for entity in self._relay_status_entities:
            if getattr(entity, "hass", None) is not None:
                entity.async_write_ha_state()
