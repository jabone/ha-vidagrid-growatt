"""Minimal REST client for the VidaGrid (Growatt white-label) portal API.

Field mapping in this file is based on a real captured response from a
live 2-inverter, no-solar Base Power account (see the "Raw Data" diagnostic
sensors this integration exposes, which is how the shapes below were
confirmed). Two distinct shapes are in play:

- `/diagram`: a flat dict of camelCase telemetry keys directly under
  `data` (e.g. `data["loadPower"]`).
- `/battery`: `data` is a list of labeled *sections*
  (`{"title": ..., "children": [{"name": ..., "value": ...}, ...]}`),
  matching the collapsible panels shown in the portal's own "Battery" tab.
  Values are looked up by their exact on-screen label (e.g. "Discharge
  Power") inside the "Summary Information" section, not by a JSON key.

Both endpoints wrap their real payload in `{"code": 0, "msg": "SUCCESS",
"data": ...}`, so this account's data always lives one level down from the
plain fetch.
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


def _payload(raw: Any) -> Any:
    """Unwrap the `{"code": 0, "msg": "SUCCESS", "data": ...}` envelope."""
    if isinstance(raw, dict) and "data" in raw:
        return raw["data"]
    return raw


def _find_section(sections: Any, title: str) -> dict[str, Any] | None:
    """Find one labeled section (by exact title) in the battery endpoint's tree."""
    if not isinstance(sections, list):
        return None
    for section in sections:
        if isinstance(section, dict) and section.get("title") == title:
            return section
    return None


def _children_by_name(section: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten a section's `children` list into a {label: value} dict."""
    result: dict[str, Any] = {}
    if not section:
        return result
    for child in section.get("children", []) or []:
        name = child.get("name")
        if name:
            result[name] = child.get("value")
    return result


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

        sections = _payload(raw)
        summary = _children_by_name(_find_section(sections, "Summary Information"))

        parsed = {
            "discharge_power_w": summary.get("Discharge Power"),
            "charge_power_w": summary.get("Charge Power"),
            "bdc1_sn": summary.get("BDC1 SN") or None,
            "bdc2_sn": summary.get("BDC2 SN") or None,
            "connect_status": summary.get("Connect Status"),
            "bus_ref_v": summary.get("Bus Ref"),
            "bms_type": summary.get("BMS Type"),
            "ac_to_load_w": summary.get("AC To Load"),
            "bdc_link_num": summary.get("BDC Link Num"),
            "pack_num": summary.get("Pack Num"),
            "raw": raw,
        }
        return parsed

    async def async_get_diagram(self, sn: str) -> dict[str, Any]:
        """Fetch the live energy-flow diagram data for one inverter."""
        raw = await self._get(EP_INVERTER_DIAGRAM.format(sn=sn))
        _LOGGER.debug("VidaGrid diagram raw response for %s: %s", sn, raw)

        data = _payload(raw)
        if not isinstance(data, dict):
            data = {}

        discharge = data.get("dischargePower") or 0
        charge = data.get("chargePower") or 0
        power_to_grid = data.get("powerToGrid") or 0
        power_to_user = data.get("powerToUser") or 0
        soc_bdc1 = data.get("socBdc1")
        soc_bdc2 = data.get("socBdc2")

        parsed = {
            "load_w": data.get("loadPower"),
            "pv_w": data.get("pvPower"),
            # Positive = importing from grid, negative = exporting to grid.
            "grid_w": (power_to_user - power_to_grid) if (power_to_user or power_to_grid) else 0,
            # Positive = battery discharging (powering the home), negative = charging.
            "battery_w": discharge - charge,
            "battery_soc_percent": soc_bdc1 if soc_bdc1 else soc_bdc2,
            # The portal itself shows "On-Grid"/"Off-Grid" based on this flag.
            "grid_status": data.get("minGridConnection"),
            "equipment_model": data.get("equipmentModel"),
            # NOTE: `is_online` in this payload was 0 even while every other
            # field reflected live, current telemetry -- matches the
            # cosmetic "Offline" bug seen in the portal's own Devices list.
            # Deliberately not used for anything; kept in raw for reference.
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
