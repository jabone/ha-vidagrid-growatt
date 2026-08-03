"""Minimal REST client for the VidaGrid (Growatt white-label) portal API.

This talks to undocumented endpoints discovered via browser network
inspection. The exact JSON field names returned by each endpoint were NOT
captured (the login page's CAPTCHA and the platform's own credential
protections meant we could only confirm endpoint paths, HTTP methods, and
that auth is a Bearer token -- not the full response schema). Because of
that, `_dig()` below searches the raw response defensively across a list of
plausible key-name variants (camelCase / snake_case / the exact label text
shown in the portal's UI) instead of assuming one fixed shape.

If a value doesn't show up under any of the guessed keys, it will simply be
None and the raw payload is still made available as `raw` on the returned
dict for diagnostics (visible via the "Raw Data" diagnostic sensors and in
debug logs), the same troubleshooting pattern used for the Base Power
integration fixes.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import (
    EP_INVERTER_BATTERY,
    EP_INVERTER_DIAGRAM,
    EP_INVERTER_PRODUCTION,
    EP_INVERTER_POWER_CURVE,
)

_LOGGER = logging.getLogger(__name__)


class VidaGridAuthError(Exception):
    """Raised when the bearer token is missing/expired/rejected (HTTP 401/403)."""


class VidaGridApiError(Exception):
    """Raised for any other non-2xx response or transport failure."""


def _dig(data: Any, *candidates: str) -> Any:
    """Best-effort lookup of a value under any of several possible key names.

    Searches the top level of `data` first, then one level of nesting into
    any dict-valued fields (covers the common "wrapped in a `data` key"
    pattern this API's billing-style endpoints have shown elsewhere).
    """
    if not isinstance(data, dict):
        return None

    for key in candidates:
        if key in data:
            return data[key]

    for value in data.values():
        if isinstance(value, dict):
            for key in candidates:
                if key in value:
                    return value[key]
    return None


class VidaGridApiClient:
    """Thin async client for the VidaGrid inverter/battery REST endpoints."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        bearer_token: str,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._token = bearer_token

    def set_token(self, bearer_token: str) -> None:
        """Update the stored bearer token (e.g. after re-auth)."""
        self._token = bearer_token

    async def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token}",
        }
        try:
            async with self._session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status in (401, 403):
                    raise VidaGridAuthError(f"Auth rejected ({resp.status}) for {path}")
                if resp.status != 200:
                    text = await resp.text()
                    raise VidaGridApiError(f"HTTP {resp.status} for {path}: {text[:200]}")
                try:
                    return await resp.json(content_type=None)
                except ValueError as err:
                    raise VidaGridApiError(f"Non-JSON response from {path}") from err
        except aiohttp.ClientError as err:
            raise VidaGridApiError(f"Network error calling {path}: {err}") from err

    async def async_validate_token(self, sample_sn: str) -> bool:
        """Return True if the token is accepted, raise VidaGridAuthError if not."""
        await self._get(EP_INVERTER_BATTERY.format(sn=sample_sn))
        return True

    async def async_get_battery(self, sn: str) -> dict[str, Any]:
        """Fetch battery-pack detail for one inverter and normalize known fields."""
        raw = await self._get(EP_INVERTER_BATTERY.format(sn=sn))
        _LOGGER.debug("VidaGrid battery raw response for %s: %s", sn, raw)

        parsed = {
            "discharge_power_w": _dig(raw, "dischargePower", "discharge_power", "dischargePowerW"),
            "charge_power_w": _dig(raw, "chargePower", "charge_power", "chargePowerW"),
            "bdc1_sn": _dig(raw, "bdc1Sn", "bdc1_sn", "bdcSn1"),
            "bdc2_sn": _dig(raw, "bdc2Sn", "bdc2_sn", "bdcSn2"),
            "connect_status": _dig(raw, "connectStatus", "connect_status"),
            "bus_ref_v": _dig(raw, "busRef", "bus_ref", "busVoltage"),
            "bms_type": _dig(raw, "bmsType", "bms_type"),
            "ac_to_load_w": _dig(raw, "acToLoad", "ac_to_load", "acToLoadW"),
            "bdc_link_num": _dig(raw, "bdcLinkNum", "bdc_link_num"),
            "pack_num": _dig(raw, "packNum", "pack_num"),
            "raw": raw,
        }
        return parsed

    async def async_get_diagram(self, sn: str) -> dict[str, Any]:
        """Fetch the live energy-flow diagram data for one inverter."""
        raw = await self._get(EP_INVERTER_DIAGRAM.format(sn=sn))
        _LOGGER.debug("VidaGrid diagram raw response for %s: %s", sn, raw)

        parsed = {
            "load_w": _dig(raw, "loadPower", "load_power", "load", "loadW"),
            "pv_w": _dig(raw, "pvPower", "pv_power", "pv", "pvW"),
            "grid_w": _dig(raw, "gridPower", "grid_power", "grid", "gridW"),
            "battery_w": _dig(raw, "batteryPower", "battery_power", "battery", "batteryW"),
            "battery_soc_percent": _dig(raw, "batterySoc", "battery_soc", "soc", "batteryPercent"),
            "grid_status": _dig(raw, "gridStatus", "grid_status", "onGrid", "status"),
            "scenario": _dig(raw, "scenario"),
            "ems_priority": _dig(raw, "emsPriority", "ems_priority"),
            "raw": raw,
        }
        return parsed

    async def async_get_production(self) -> dict[str, Any]:
        """Fetch the fleet-wide production summary (all inverters on the account)."""
        raw = await self._get(EP_INVERTER_PRODUCTION)
        _LOGGER.debug("VidaGrid production raw response: %s", raw)
        return {"raw": raw}

    async def async_get_power_curve(self, sn: str) -> dict[str, Any]:
        """Fetch the historical power curve for one inverter (today, by default)."""
        raw = await self._get(EP_INVERTER_POWER_CURVE.format(sn=sn))
        _LOGGER.debug("VidaGrid power curve raw response for %s: %s", sn, raw)
        return {"raw": raw}
