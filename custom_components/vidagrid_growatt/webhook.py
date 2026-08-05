"""Webhook ingest endpoint for the VidaGrid Growatt integration.

Receives telemetry pushed by the browser-side userscript (see README.md)
running in the user's own already-authenticated VidaGrid browser tab. The
userscript reads whatever bearer token the page currently holds *locally*
to fetch fresh `/battery`, `/diagram`, `/flows/curve/power`, and
`/flows/curve/energy` JSON, then POSTs only that data here -- the token
itself never leaves the user's browser.

Expected POST body (JSON):
    {
        "sn": "SMN7T5N0WN",
        "battery": { ...raw /battery response... },                     # optional
        "diagram": { ...raw /diagram response... },                     # optional
        "power_curve": { ...raw /flows/curve/power response... },       # optional
        "energy_curve": { ...raw /flows/curve/energy response... }      # optional
    }

The webhook_id is generated once per config entry (see __init__.py) and is
unauthenticated like any standard Home Assistant webhook -- treat the full
URL as a shared secret (don't post it publicly).
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.core import HomeAssistant

from .coordinator import VidaGridCoordinator

_LOGGER = logging.getLogger(__name__)


async def _handle_webhook(
    hass: HomeAssistant, webhook_id: str, request: web.Request
) -> web.Response:
    coordinator: VidaGridCoordinator | None = hass.data.get("vidagrid_growatt_webhooks", {}).get(
        webhook_id
    )
    if coordinator is None:
        _LOGGER.warning(
            "Webhook hit for id=%s but no coordinator is registered for it "
            "(known ids: %s) -- this entry may be stale from a previous load",
            webhook_id,
            list(hass.data.get("vidagrid_growatt_webhooks", {}).keys()),
        )
        return web.Response(status=404, text="unknown webhook")

    try:
        payload: dict[str, Any] = await request.json()
    except ValueError:
        return web.Response(status=400, text="invalid json")

    sn = payload.get("sn")
    if not sn or sn not in coordinator.inverter_sns:
        _LOGGER.warning(
            "Webhook hit with sn=%r not in known inverter_sns=%s",
            sn,
            coordinator.inverter_sns,
        )
        return web.Response(status=400, text="missing or unknown 'sn'")

    battery_raw = payload.get("battery")
    diagram_raw = payload.get("diagram")
    power_curve_raw = payload.get("power_curve")
    energy_curve_raw = payload.get("energy_curve")
    if (
        battery_raw is None
        and diagram_raw is None
        and power_curve_raw is None
        and energy_curve_raw is None
    ):
        return web.Response(
            status=400,
            text="need 'battery', 'diagram', 'power_curve', and/or 'energy_curve'",
        )

    _LOGGER.warning(
        "Webhook ingest starting: sn=%s coordinator_id=%s listeners=%d "
        "has_battery=%s has_diagram=%s has_power_curve=%s has_energy_curve=%s",
        sn,
        id(coordinator),
        len(coordinator._listeners) if hasattr(coordinator, "_listeners") else -1,
        battery_raw is not None,
        diagram_raw is not None,
        power_curve_raw is not None,
        energy_curve_raw is not None,
    )

    try:
        coordinator.ingest(
            sn,
            battery_raw=battery_raw,
            diagram_raw=diagram_raw,
            power_curve_raw=power_curve_raw,
            energy_curve_raw=energy_curve_raw,
        )
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Failed to ingest webhook payload for %s", sn)
        return web.Response(status=500, text="ingest failed")

    _LOGGER.warning(
        "Webhook ingest finished: sn=%s coordinator_id=%s new_battery_soc=%s",
        sn,
        id(coordinator),
        (coordinator.data.get(sn, {}).get("diagram") or {}).get("battery_soc_percent")
        if coordinator.data
        else None,
    )

    return web.Response(status=200, text="ok")


def register(hass: HomeAssistant, webhook_id: str, coordinator: VidaGridCoordinator) -> None:
    """Register this config entry's webhook and track its coordinator."""
    existing = hass.data.get("vidagrid_growatt_webhooks", {}).get(webhook_id)
    _LOGGER.warning(
        "Registering webhook id=%s coordinator_id=%s (replacing existing coordinator_id=%s)",
        webhook_id,
        id(coordinator),
        id(existing) if existing is not None else None,
    )
    hass.data.setdefault("vidagrid_growatt_webhooks", {})[webhook_id] = coordinator
    webhook.async_register(
        hass,
        "vidagrid_growatt",
        "VidaGrid data ingest",
        webhook_id,
        _handle_webhook,
    )


def unregister(hass: HomeAssistant, webhook_id: str) -> None:
    """Unregister a webhook on unload/removal."""
    _LOGGER.warning("Unregistering webhook id=%s", webhook_id)
    webhook.async_unregister(hass, webhook_id)
    hass.data.get("vidagrid_growatt_webhooks", {}).pop(webhook_id, None)
