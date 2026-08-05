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
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VidaGridCoordinator

# All sections a dynamic field sensor / raw diagnostic sensor may come from.
_DYNAMIC_SECTIONS: tuple[str, ...] = ("battery", "diagram", "power_curve", "energy_curve")


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


# Maps a field's own reported unit string to (device_class, HA unit constant).
# Anything not found here falls back to (None, the raw unit string as-is),
# which still renders fine in HA -- it just won't get device-class-specific
# formatting/graphing.
_UNIT_TO_DEVICE_CLASS: dict[str, tuple[SensorDeviceClass | None, str | None]] = {
    "W": (SensorDeviceClass.POWER, UnitOfPower.WATT),
    "V": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
    "A": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
    "kWh": (SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR),
    "%": (None, PERCENTAGE),
    "â": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    "Â°C": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
}

# Fields whose *label* (not unit) marks them as internal/diagnostic detail --
# protocol numbers, fault/warning/debug codes, firmware/software versions,
# cell-index pointers, etc. -- kept out of the main dashboard view even
# though some of them carry a normal-looking unit.
_DIAGNOSTIC_LABEL_HINTS = (
    "debug", "fault", "warn", "error", "protect", "software", "firmware",
    "version", "cell no", "cycle", "protocol", "manufacturer", "request flag",
    "wakeup", "type id", "cluster", "comm id", "derated mode", "sub code",
    "status", "history", "board", "auth version", "permillage", "internal state",
    "sn", "model", "code",
)


def _entity_category_for(label: str) -> EntityCategory | None:
    label_lower = label.lower()
    if any(hint in label_lower for hint in _DIAGNOSTIC_LABEL_HINTS):
        return EntityCategory.DIAGNOSTIC
    return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VidaGridCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []
    for sn in coordinator.inverter_sns:
        for description in SENSOR_TYPES:
            entities.append(VidaGridSensor(coordinator, entry, sn, description))
        for section_name in _DYNAMIC_SECTIONS:
            entities.append(VidaGridRawDataSensor(coordinator, entry, sn, section_name))

    async_add_entities(entities)

    # Comprehensive field coverage: every leaf metric the battery/diagram/
    # power_curve/energy_curve endpoints return gets its own entity. The
    # pasted-token fallback poll that normally populates coordinator.data
    # before this function even runs is unreliable (the token is frequently
    # already expired by the time HA restarts), so entity discovery can't
    # just happen once here -- it also has to react to every later
    # coordinator update, since that's what the frequent, reliable webhook
    # push actually drives. Re-running this on each update and skipping
    # already-known (section, field_key) pairs means new fields get added
    # exactly once, whenever the data carrying them first successfully
    # arrives -- covering both a lucky fresh-token poll at startup and the
    # ordinary webhook-only case.
    known_fields: dict[str, set[tuple[str, str]]] = {sn: set() for sn in coordinator.inverter_sns}

    @callback
    def _discover_new_fields() -> None:
        new_entities: list[SensorEntity] = []
        for sn in coordinator.inverter_sns:
            data = coordinator.data.get(sn) if coordinator.data else None
            if not data:
                continue
            for section_name in _DYNAMIC_SECTIONS:
                section = data.get(section_name) or {}
                for field_key, field in (section.get("fields") or {}).items():
                    dedup_key = (section_name, field_key)
                    if dedup_key in known_fields[sn]:
                        continue
                    known_fields[sn].add(dedup_key)
                    new_entities.append(
                        VidaGridFieldSensor(
                            coordinator,
                            sn,
                            section_name,
                            field_key,
                            field.get("label") or field_key,
                            field.get("unit") or "",
                        )
                    )
        if new_entities:
            async_add_entities(new_entities)

    _discover_new_fields()
    entry.async_on_unload(coordinator.async_add_listener(_discover_new_fields))


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
        coordinator.register_entity(sn, self)

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data.get(self._sn) if self.coordinator.data else None
        if not data:
            return None
        section = data.get(self.entity_description.section)
        if not section:
            return None
        return section.get(self.entity_description.value_key)


class VidaGridFieldSensor(CoordinatorEntity[VidaGridCoordinator], SensorEntity):
    """A dynamically-discovered field from a raw battery/diagram/curve payload.

    Covers everything the hand-picked VidaGridSensor entries above don't --
    per-battery-pack diagnostics (APX BM1..BM5: SOC/SOH/voltage/current/
    temperature/cycle count/etc.), BDC-level detail, any other /diagram
    field beyond Load/Solar Power, today's cumulative energy totals
    (production, load consumption, grid import/export, charge/discharge --
    from /flows/curve/energy), and the latest instantaneous-power snapshot
    (from /flows/curve/power). Unit and device class are inferred from the
    field's own reported unit string rather than hand-declared, since there
    are hundreds of these across all four endpoints.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VidaGridCoordinator,
        sn: str,
        section: str,
        field_key: str,
        label: str,
        unit: str,
    ) -> None:
        super().__init__(coordinator)
        self._sn = sn
        self._section = section
        self._field_key = field_key
        self._attr_name = label
        self._attr_unique_id = f"{sn}_{section}_field_{field_key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, sn)},
            "name": f"Growatt Inverter {sn}",
            "manufacturer": "Growatt",
            "model": "VidaGrid-managed inverter/battery",
        }

        device_class, ha_unit = _UNIT_TO_DEVICE_CLASS.get(unit, (None, unit or None))
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = ha_unit
        if device_class in (
            SensorDeviceClass.POWER,
            SensorDeviceClass.VOLTAGE,
            SensorDeviceClass.CURRENT,
            SensorDeviceClass.TEMPERATURE,
        ):
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif device_class == SensorDeviceClass.ENERGY:
            # These are lifetime/daily cumulative counters (e.g. "Discharge
            # Energy(Total)", "Bm Charge Cap Total") -- TOTAL_INCREASING
            # handles both never-resets and resets-to-zero-then-climbs.
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        elif ha_unit == PERCENTAGE:
            self._attr_state_class = SensorStateClass.MEASUREMENT

        self._attr_entity_category = _entity_category_for(label)
        coordinator.register_entity(sn, self)

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data.get(self._sn) if self.coordinator.data else None
        if not data:
            return None
        section = data.get(self._section)
        if not section:
            return None
        field = (section.get("fields") or {}).get(self._field_key)
        return field.get("value") if field else None


class VidaGridRawDataSensor(CoordinatorEntity[VidaGridCoordinator], SensorEntity):
    """Exposes a full raw JSON payload as attributes for diagnostics.

    Because the exact response schema wasn't fully captured from the portal
    for every endpoint (see api.py), this sensor makes the raw payload
    visible in Developer Tools > States so field mappings in api.py can be
    refined later without needing another browser-inspection session.
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
        self._attr_name = f"Raw {section.replace('_', ' ').title()} Data"
        self._attr_unique_id = f"{sn}_raw_{section}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, sn)},
            "name": f"Growatt Inverter {sn}",
            "manufacturer": "Growatt",
            "model": "VidaGrid-managed inverter/battery",
        }
        coordinator.register_entity(sn, self)

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
