"""Sensor entities for the VidaGrid Growatt integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfElectricPotential, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VidaGridCoordinator


@dataclass(frozen=True, kw_only=True)
class VidaGridSensorDescription(SensorEntityDescription):
    """Describes a VidaGrid sensor: which sub-dict and key to read."""

    section: str = "diagram"  # "diagram" or "battery"
    value_key: str = ""


SENSOR_TYPES: tuple[VidaGridSensorDescription, ...] = (
    VidaGridSensorDescription(
        key="load_power",
        translation_key="load_power",
        name="Load Power",
        section="diagram",
        value_key="load_w",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    VidaGridSensorDescription(
        key="pv_power",
        translation_key="pv_power",
        name="Solar Power",
        section="diagram",
        value_key="pv_w",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    VidaGridSensorDescription(
        key="grid_power",
        translation_key="grid_power",
        name="Grid Power",
        section="diagram",
        value_key="grid_w",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    VidaGridSensorDescription(
        key="battery_power",
        translation_key="battery_power",
        name="Battery Power",
        section="diagram",
        value_key="battery_w",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    VidaGridSensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        name="Battery Level",
        section="diagram",
        value_key="battery_soc_percent",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    VidaGridSensorDescription(
        key="discharge_power",
        translation_key="discharge_power",
        name="Battery Discharge Power",
        section="battery",
        value_key="discharge_power_w",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    VidaGridSensorDescription(
        key="charge_power",
        translation_key="charge_power",
        name="Battery Charge Power",
        section="battery",
        value_key="charge_power_w",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    VidaGridSensorDescription(
        key="bus_ref_voltage",
        translation_key="bus_ref_voltage",
        name="Battery Bus Reference Voltage",
        section="battery",
        value_key="bus_ref_v",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VidaGridSensorDescription(
        key="bms_type",
        translation_key="bms_type",
        name="Battery BMS Type",
        section="battery",
        value_key="bms_type",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VidaGridSensorDescription(
        key="pack_num",
        translation_key="pack_num",
        name="Battery Pack Count",
        section="battery",
        value_key="pack_num",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VidaGridSensorDescription(
        key="connect_status",
        translation_key="connect_status",
        name="Battery Connect Status",
        section="battery",
        value_key="connect_status",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VidaGridCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []
    for sn in coordinator.inverter_sns:
        for description in SENSOR_TYPES:
            entities.append(VidaGridSensor(coordinator, entry, sn, description))
        entities.append(VidaGridRawDataSensor(coordinator, entry, sn, "battery"))
        entities.append(VidaGridRawDataSensor(coordinator, entry, sn, "diagram"))

    async_add_entities(entities)


class VidaGridSensor(CoordinatorEntity[VidaGridCoordinator], SensorEntity):
    """A single derived value read from the battery or diagram payload."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VidaGridCoordinator,
        entry: ConfigEntry,
        sn: str,
        description: VidaGridSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._sn = sn
        self._attr_unique_id = f"{sn}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, sn)},
            "name": f"Growatt Inverter {sn}",
            "manufacturer": "Growatt",
            "model": "VidaGrid-managed inverter/battery",
        }

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data.get(self._sn) if self.coordinator.data else None
        if not data:
            return None
        section = data.get(self.entity_description.section)
        if not section:
            return None
        return section.get(self.entity_description.value_key)


class VidaGridRawDataSensor(CoordinatorEntity[VidaGridCoordinator], SensorEntity):
    """Exposes the full raw JSON payload as attributes for diagnostics.

    Because the exact response schema wasn't fully captured from the portal
    (see api.py), this sensor makes the raw payload visible in Developer
    Tools > States so field mappings in api.py can be refined later without
    needing another browser-inspection session.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: VidaGridCoordinator, entry: ConfigEntry, sn: str, section: str
    ) -> None:
        super().__init__(coordinator)
        self._sn = sn
        self._section = section
        self._attr_name = f"Raw {section.capitalize()} Data"
        self._attr_unique_id = f"{sn}_raw_{section}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, sn)},
            "name": f"Growatt Inverter {sn}",
            "manufacturer": "Growatt",
            "model": "VidaGrid-managed inverter/battery",
        }

    @property
    def native_value(self) -> Any:
        return "ok" if self._get_raw() is not None else "unavailable"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        raw = self._get_raw()
        return {"raw": raw} if raw is not None else None

    def _get_raw(self) -> Any:
        data = self.coordinator.data.get(self._sn) if self.coordinator.data else None
        if not data:
            return None
        section = data.get(self._section)
        return section.get("raw") if section else None
