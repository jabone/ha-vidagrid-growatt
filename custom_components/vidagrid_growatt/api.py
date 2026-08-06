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
  A handful of "multiple"-type sections (BDC, APX) nest one level deeper:
  their children are themselves named sub-sections (BDC's "Information"
  and "BDC1", APX's "APX BM1".."APX BM5" -- one per physical battery
  pack) that each hold the actual leaf metrics.

Both endpoints wrap their real payload in `{"code": 0, "msg": "SUCCESS",
"data": ...}`, so this account's data always lives one level down from the
plain fetch.

Beyond the handful of named fields kept for backward compatibility with
the original sensor set, both parsers also return a "fields" dict holding
*every* leaf metric they found (keyed by a sanitized snake_case name, with
the original on-screen label and unit preserved) so sensor.py can surface
the full breadth of what the portal shows -- individual battery-pack
diagnostics (APX BM1..BM5), BDC-level detail, etc. -- without this file
needing an explicit line of code per field.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from .const import (
    EP_INVERTER_BATTERY,
    EP_INVERTER_DIAGRAM,
    EP_INVERTER_ENERGY_CURVE,
    EP_INVERTER_POWER_CURVE,
    EP_INVERTER_PRODUCTION,
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


def _sanitize_key(label: str) -> str:
    """Turn a human label like 'AC To Load' or 'APX BM1  SOC' into a snake_case key."""
    s = label.strip().lower()
    s = re.sub(r"[^\w]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "field"


# Labels already surfaced by the small set of hand-picked, well-typed sensors
# below (Discharge Power, Load Power, etc.) -- skipped when flattening so the
# comprehensive "fields" dict doesn't duplicate them under a second entity.
_STATICALLY_COVERED_BATTERY_LABELS = {
    "Discharge Power",
    "Charge Power",
    "BDC1 SN",
    "BDC2 SN",
    "Connect Status",
    "Bus Ref",
    "BMS Type",
    "AC To Load",
    "BDC Link Num",
    "Pack Num",
}
_STATICALLY_COVERED_DIAGRAM_KEYS = {"loadPower", "pvPower"}


def _flatten_battery_sections(sections: Any) -> dict[str, dict[str, Any]]:
    """Flatten every leaf metric in the /battery endpoint's section tree.

    Returns {sanitized_key: {"label": display label, "unit": str, "value": Any}}.
    Leaf names inside nested sub-sections (BDC1, APX BM1..BM5) are often
    generic/un-prefixed on their own (e.g. " SOC", " Voltage"), so they're
    prefixed with their sub-section's own title to keep e.g. "APX BM1 SOC"
    and "APX BM2 SOC" distinct entities instead of colliding.
    """
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(sections, list):
        return result

    def _add_leaf(label: str, leaf: dict[str, Any]) -> None:
        label = label.strip()
        if not label or label in _STATICALLY_COVERED_BATTERY_LABELS:
            return
        key = _sanitize_key(label)
        base_key, suffix = key, 2
        while key in result and result[key]["label"] != label:
            key = f"{base_key}_{suffix}"
            suffix += 1
        result[key] = {
            "label": label,
            "unit": (leaf.get("unit") or "").strip(),
            "value": leaf.get("value"),
        }

    for section in sections:
        if not isinstance(section, dict):
            continue
        for child in section.get("children") or []:
            if not isinstance(child, dict):
                continue
            if "children" in child:
                # Nested sub-section: BDC's "Information"/"BDC1", APX's "APX BM1".."BM5".
                sub_title = (child.get("title") or "").strip()
                for leaf in child.get("children") or []:
                    if not isinstance(leaf, dict) or "value" not in leaf:
                        continue
                    name = (leaf.get("name") or "").strip()
                    if not name:
                        continue
                    label = f"{sub_title} {name}".strip() if sub_title else name
                    _add_leaf(label, leaf)
            elif "value" in child:
                name = (child.get("name") or "").strip()
                if name:
                    _add_leaf(name, child)
    return result


def _infer_diagram_unit(key: str) -> str:
    """Best-effort unit guess for /diagram fields, which carry no unit metadata."""
    k = key.lower()
    if "power" in k:
        return "W"
    if "energy" in k or k.endswith("kwh"):
        return "kWh"
    if "soc" in k or "percent" in k:
        return "%"
    if "voltage" in k or k.endswith("volt"):
        return "V"
    if "current" in k:
        return "A"
    if "temp" in k:
        return "°C"
    return ""


def parse_battery_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw `/battery` endpoint response into known fields.

    Pure function (no I/O) so it can be shared by both the polling HTTP
    client below and the webhook handler in webhook.py, which receives the
    same raw JSON shape pushed from the browser userscript instead of
    fetching it itself.
    """
    sections = _payload(raw)
    summary = _children_by_name(_find_section(sections, "Summary Information"))
    fields = _flatten_battery_sections(sections)

    return {
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
        "fields": fields,
        "raw": raw,
    }


def parse_diagram_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw `/diagram` endpoint response into known fields.

    Pure function -- see parse_battery_raw() docstring.
    """
    data = _payload(raw)
    if not isinstance(data, dict):
        data = {}

    discharge = data.get("dischargePower") or 0
    charge = data.get("chargePower") or 0
    power_to_grid = data.get("powerToGrid") or 0
    power_to_user = data.get("powerToUser") or 0
    soc_bdc1 = data.get("socBdc1")
    soc_bdc2 = data.get("socBdc2")

    fields: dict[str, dict[str, Any]] = {}
    for k, v in data.items():
        if k in _STATICALLY_COVERED_DIAGRAM_KEYS:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        fields[_sanitize_key(k)] = {
            "label": k,
            "unit": _infer_diagram_unit(k),
            "value": v,
        }

    return {
        "load_w": data.get("loadPower"),
        "pv_w": data.get("pvPower"),
        # Positive = importing from grid, negative = exporting to grid.
        "grid_w": (power_to_user - power_to_grid)
        if (power_to_user or power_to_grid)
        else 0,
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
        "fields": fields,
        "raw": raw,
    }


def _day_range_params(now: datetime, days_ago: int = 0) -> dict[str, str]:
    """Build the startTime/endTime/type query params both curve endpoints require.

    Confirmed via live browser network capture on 2026-08-04: the portal's own
    "Energy&Power" tab calls both endpoints with startTime/endTime set to the
    start/end of the selected day (ISO 8601, with the browser's own UTC
    offset -- e.g. "2026-08-04T00:00:00-05:00") plus type=5m for 5-minute
    granularity. Without these params both endpoints return HTTP 200 with an
    empty/null "data" -- that empty response is what this integration got the
    first time it wired these endpoints in, before the params were known.

    `days_ago` shifts the queried calendar day back (0 = today, 1 =
    yesterday, ...) -- see async_get_power_curve()/async_get_energy_curve()
    for why that matters on some accounts.
    """
    target = now - timedelta(days=days_ago)
    start = target.replace(hour=0, minute=0, second=0, microsecond=0)
    end = target.replace(hour=23, minute=59, second=59, microsecond=0)
    return {"startTime": start.isoformat(), "endTime": end.isoformat(), "type": "5m"}


def _flatten_flat_numeric_dict(
    data: dict[str, Any], skip_keys: set[str] | None = None
) -> dict[str, dict[str, Any]]:
    """Flatten a flat dict of numeric telemetry into the common {key: {label, unit, value}} shape.

    Shared by parse_diagram_raw and the two curve parsers below -- all three
    endpoints return a flat dict of camelCase/snake_case numeric fields with
    no unit metadata, so unit is guessed the same way in all three cases.
    """
    skip_keys = skip_keys or set()
    fields: dict[str, dict[str, Any]] = {}
    for k, v in data.items():
        if k in skip_keys:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        fields[_sanitize_key(k)] = {
            "label": k,
            "unit": _infer_diagram_unit(k),
            "value": v,
        }
    return fields


def _parse_curve_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Shared parser for both `/flows/curve/power` and `/flows/curve/energy`.

    Confirmed via live capture: `data` is a list of timestamped snapshots
    (one per interval across the requested day, e.g. every 5 minutes per
    `type=5m`), each a flat dict of numeric fields -- `/power` holds
    instantaneous readings (ppv, pacToUserTotal, discharge_power, ...),
    `/energy` holds day-running cumulative totals (epvToday, eacToday,
    elocalLoadToday, echargeToday, edischargeToday, socBdc1, ...). Only the
    most recent (last) snapshot is surfaced as sensor fields -- exposing the
    full list as ~300 individual entities per inverter isn't useful, and the
    latest point is what a dashboard actually wants. The full list is still
    kept under "raw" for reference/future use (e.g. a proper history graph).
    """
    data = _payload(raw)
    latest = data[-1] if isinstance(data, list) and data else None
    fields = _flatten_flat_numeric_dict(latest) if isinstance(latest, dict) else {}
    return {"fields": fields, "latest": latest, "raw": raw}


def _curve_has_data(raw: dict[str, Any] | None) -> bool:
    """True if a curve endpoint's response actually carries any data points."""
    if not raw:
        return False
    data = _payload(raw)
    return bool(data)


def parse_power_curve_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw `/flows/curve/power` response (instantaneous power history)."""
    return _parse_curve_raw(raw)


def parse_energy_curve_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw `/flows/curve/energy` response (portal's "Energy" tab totals)."""
    return _parse_curve_raw(raw)


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

    async def _get(
        self, path: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token}",
        }
        try:
            async with self._session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status in (401, 403):
                    raise VidaGridAuthError(f"Auth rejected ({resp.status}) for {path}")
                if resp.status != 200:
                    text = await resp.text()
                    raise VidaGridApiError(
                        f"HTTP {resp.status} for {path}: {text[:200]}"
                    )
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
        return parse_battery_raw(raw)

    async def async_get_diagram(self, sn: str) -> dict[str, Any]:
        """Fetch the live energy-flow diagram data for one inverter."""
        raw = await self._get(EP_INVERTER_DIAGRAM.format(sn=sn))
        _LOGGER.debug("VidaGrid diagram raw response for %s: %s", sn, raw)
        return parse_diagram_raw(raw)

    async def async_get_production(self) -> dict[str, Any]:
        """Fetch the fleet-wide production summary (all inverters on the account)."""
        raw = await self._get(EP_INVERTER_PRODUCTION)
        _LOGGER.debug("VidaGrid production raw response: %s", raw)
        return {"raw": raw}

    async def _async_get_curve_with_fallback(
        self, endpoint: str, sn: str, now: datetime
    ) -> dict[str, Any]:
        """Fetch a curve endpoint for today, falling back to yesterday if empty.

        Some accounts' curve/history rollup lags a day behind -- today's
        range comes back HTTP 200 with "data": null even with valid params
        and a healthy token (confirmed by comparing against the portal's own
        Energy&Power tab, which itself defaults to showing yesterday when
        opened). Try today first since that's what most accounts should
        have, then fall back to yesterday once before giving up, rather than
        returning a permanently empty result.
        """
        raw = await self._get(endpoint.format(sn=sn), params=_day_range_params(now, 0))
        if _curve_has_data(raw):
            return raw
        _LOGGER.debug(
            "VidaGrid curve endpoint %s returned no data for today (sn=%s); "
            "retrying with yesterday's date range",
            endpoint,
            sn,
        )
        return await self._get(endpoint.format(sn=sn), params=_day_range_params(now, 1))

    async def async_get_power_curve(self, sn: str, now: datetime) -> dict[str, Any]:
        """Fetch today's instantaneous-power history for one inverter, or yesterday's if empty.

        `now` should be a tz-aware datetime in the account's local timezone
        (e.g. Home Assistant's own `dt_util.now()` ) -- the endpoint requires
        startTime/endTime with an explicit UTC offset, confirmed via live
        browser network capture (see _day_range_params()).
        """
        raw = await self._async_get_curve_with_fallback(
            EP_INVERTER_POWER_CURVE, sn, now
        )
        _LOGGER.debug("VidaGrid power curve raw response for %s: %s", sn, raw)
        return parse_power_curve_raw(raw)

    async def async_get_energy_curve(self, sn: str, now: datetime) -> dict[str, Any]:
        """Fetch today's cumulative energy totals for one inverter, or yesterday's if empty.

        See async_get_power_curve() docstring re: the `now` param.
        """
        raw = await self._async_get_curve_with_fallback(
            EP_INVERTER_ENERGY_CURVE, sn, now
        )
        _LOGGER.debug("VidaGrid energy curve raw response for %s: %s", sn, raw)
        return parse_energy_curve_raw(raw)
