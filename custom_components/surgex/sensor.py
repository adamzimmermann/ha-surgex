"""Measurement and diagnostic sensors for the SurgeX integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import SurgexConfigEntry, SurgexCoordinator
from .entity import SurgexEntity
from .models import SquidStatus


@dataclass(frozen=True, kw_only=True)
class SurgexSensorEntityDescription(SensorEntityDescription):
    """Describes a SurgeX sensor and how to read it from a snapshot."""

    value_fn: Callable[[SquidStatus], StateType]


SENSORS: tuple[SurgexSensorEntityDescription, ...] = (
    SurgexSensorEntityDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda s: s.measurements.power,
    ),
    SurgexSensorEntityDescription(
        key="current",
        translation_key="current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=lambda s: s.measurements.current,
    ),
    SurgexSensorEntityDescription(
        key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value_fn=lambda s: s.measurements.voltage,
    ),
    SurgexSensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        # Celsius unconditionally: this firmware reports temperatureUnits "F"
        # while emitting an obviously Celsius value.
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda s: s.measurements.temperature_c,
    ),
    SurgexSensorEntityDescription(
        key="frequency",
        translation_key="frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.measurements.frequency,
    ),
    SurgexSensorEntityDescription(
        key="power_factor",
        translation_key="power_factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: (
            None if s.measurements.power_factor is None
            else round(s.measurements.power_factor * 100, 1)
        ),
    ),
    SurgexSensorEntityDescription(
        key="input_state",
        translation_key="input_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.input_state,
    ),
)

ENERGY_DESCRIPTION = SurgexSensorEntityDescription(
    key="energy",
    translation_key="energy",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
    value_fn=lambda s: s.measurements.energy_wh,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurgexConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create sensors for whatever the device actually reports."""
    coordinator = entry.runtime_data
    status = coordinator.data

    entities: list[SensorEntity] = [
        SurgexSensor(coordinator, description)
        for description in SENSORS
        # Skip entities the device has no data for rather than showing unknowns.
        if description.value_fn(status) is not None
    ]

    if status.measurements.energy_wh is not None:
        entities.append(SurgexEnergySensor(coordinator, ENERGY_DESCRIPTION))

    async_add_entities(entities)


class SurgexSensor(SurgexEntity, SensorEntity):
    """A single measurement read from the snapshot."""

    entity_description: SurgexSensorEntityDescription

    def __init__(
        self,
        coordinator: SurgexCoordinator,
        description: SurgexSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.status)


class SurgexEnergySensor(SurgexSensor):
    """Cumulative energy, which the user can reset on the device."""

    @property
    def last_reset(self) -> datetime | None:
        """When the device's counter was last zeroed.

        Reporting this lets Home Assistant treat a reset as a reset rather than
        misreading it as a counter rollover.
        """
        return self.status.measurements.energy_reset
