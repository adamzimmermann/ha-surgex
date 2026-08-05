"""Base entity for the SurgeX integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SurgexCoordinator
from .models import SquidStatus


class SurgexEntity(CoordinatorEntity[SurgexCoordinator]):
    """Common device identity and availability for every SurgeX entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SurgexCoordinator, key: str) -> None:
        super().__init__(coordinator)
        status = coordinator.data
        self._attr_unique_id = f"{status.unique_id}_{key}"

        info = DeviceInfo(
            identifiers={(DOMAIN, status.unique_id)},
            manufacturer=MANUFACTURER,
            model=status.model,
            name=status.hostname or status.model,
            sw_version=status.firmware,
            configuration_url=coordinator.client.base_url,
        )
        # The live unit reports an empty serial; omit rather than show a blank.
        if status.serial:
            info["serial_number"] = status.serial
        self._attr_device_info = info

    @property
    def status(self) -> SquidStatus:
        """The most recent parsed snapshot."""
        return self.coordinator.data
