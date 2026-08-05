"""Surge and wiring diagnostics for the SurgeX integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SurgexConfigEntry, SurgexCoordinator
from .entity import SurgexEntity
from .models import SquidStatus


@dataclass(frozen=True, kw_only=True)
class SurgexBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a SurgeX binary sensor."""

    # True means "there is a problem", matching device_class PROBLEM.
    value_fn: Callable[[SquidStatus], bool | None]
    available_fn: Callable[[SquidStatus], bool]


BINARY_SENSORS: tuple[SurgexBinarySensorEntityDescription, ...] = (
    SurgexBinarySensorEntityDescription(
        key="surge_protection",
        translation_key="surge_protection",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        # surgeGood true is healthy, so invert for a PROBLEM sensor.
        value_fn=lambda s: (
            None if s.measurements.surge_good is None else not s.measurements.surge_good
        ),
        available_fn=lambda s: s.measurements.surge_good is not None,
    ),
    SurgexBinarySensorEntityDescription(
        key="wiring_fault",
        translation_key="wiring_fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.wiring_fault,
        available_fn=lambda s: s.wiring_fault is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurgexConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create only the diagnostics this firmware actually reports."""
    coordinator = entry.runtime_data
    status = coordinator.data
    async_add_entities(
        SurgexBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if description.available_fn(status)
    )


class SurgexBinarySensor(SurgexEntity, BinarySensorEntity):
    """A problem indicator derived from the snapshot."""

    entity_description: SurgexBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: SurgexCoordinator,
        description: SurgexBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.status)
