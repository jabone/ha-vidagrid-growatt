"""Webhook ingest endpoint for the VidaGrid Growatt integration.

Receives telemetry pushed by the browser-side userscript (see README.md)
running in the user's own already-authenticated VidaGrid browser tab. The
userscript reads whatever bearer token the page currently holds *locally*
to fetch fresh `/battery` and `/diagram` JSON, then POSTs only that data
here -- the token itself never leaves the user's browser.

Expected POST body (JSON):
    {
        "sn": "SN00000001",
        "battery": { ...raw /battery response... },   # optional
        "diagram": { ...raw /diagram response... }     # optional
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
        return web.Response(status=404, text="unknown webhook")

    try:
        payload: dict[str, Any] = await request.json()
    except ValueError:
        return web.Response(status=400, text="invalid json")

    sn = payload.get("sn")
    if not sn or sn not in coordinator.inverter_sns:
        return web.Response(status=400, text="missing or unknown 'sn'")

    battery_raw = payload.get("battery")
    diagram_raw = payload.get("diagram")
    if battery_raw is None and diagram_raw is None:
        return web.Response(status=400, text="need 'battery' and/or 'diagram'")

    try:
        coordinator.ingest(sn, battery_raw=battery_raw, diagram_raw=diagram_raw)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Failed to ingest webhook payload for %s", sn)
        return web.Response(status=500, text="ingest failed")

    return web.Response(status=200, text="ok")


def register(hass: HomeAssistant, webhook_id: str, coordinator: VidaGridCoordinator) -> None:
    """Register this config entry's webhook and track its coordinator."""
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
    webhook.async_unregister(hass, webhook_id)
    hass.data.get("vidagrid_growatt_webhooks", {}).pop(webhook_id, None)
