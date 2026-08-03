"""Binary sensor entities for the VidaGrid Growatt integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VidaGridCoordinator

# Observed values on the portal UI were the strings "On-Grid" / "Off-Grid".
# Kept as a set in case the API instead returns booleans or different casing.
_ON_GRID_TRUE_VALUES = {"on-grid", "ongrid", "on", "true", "1", True, 1}
_ON_GRID_FALSE_VALUES = {"off-grid", "offgrid", "off", "false", "0", False, 0}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VidaGridCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [VidaGridGridStatusSensor(coordinator, entry, sn) for sn in coordinator.inverter_sns]
    async_add_entities(entities)


class VidaGridGridStatusSensor(CoordinatorEntity[VidaGridCoordinator], BinarySensorEntity):
    """On when the inverter reports On-Grid, off when Off-Grid, unknown otherwise.

    Unlike the Base Power grid sensor (see upstream PR #5), this defaults to
    unknown (None) whenever the raw value can't be confidently interpreted,
    rather than guessing "grid is up" -- the same safety reasoning applies
    here: a false "grid is fine" reading during an actual outage is worse
    than an honest "unknown".
    """

    _attr_has_entity_name = True
    _attr_name = "Grid Status"
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, coordinator: VidaGridCoordinator, entry: ConfigEntry, sn: str) -> None:
        super().__init__(coordinator)
        self._sn = sn
        self._attr_unique_id = f"{sn}_grid_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, sn)},
            "name": f"Growatt Inverter {sn}",
            "manufacturer": "Growatt",
            "model": "VidaGrid-managed inverter/battery",
        }

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data.get(self._sn) if self.coordinator.data else None
        if not data or not data.get("diagram"):
            return None
        raw_status = data["diagram"].get("grid_status")
        if raw_status is None:
            return None
        normalized = raw_status.strip().lower() if isinstance(raw_status, str) else raw_status
        if normalized in _ON_GRID_TRUE_VALUES:
            return True
        if normalized in _ON_GRID_FALSE_VALUES:
            return False
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data.get(self._sn) if self.coordinator.data else None
        if not data or not data.get("diagram"):
            return None
        return {"raw_grid_status": data["diagram"].get("grid_status")}
