"""Reboot and maintenance buttons for the SurgeX integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SurgexConfigEntry, SurgexCoordinator
from .entity import SurgexEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurgexConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create a reboot button per outlet, plus one energy reset."""
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = [
        SurgexRebootButton(coordinator, outlet.id) for outlet in coordinator.data.outlets
    ]
    entities.append(SurgexResetEnergyButton(coordinator))
    async_add_entities(entities)


class SurgexRebootButton(SurgexEntity, ButtonEntity):
    """Power-cycles one outlet using the device's own reboot delay."""

    _attr_device_class = ButtonDeviceClass.RESTART

    def __init__(self, coordinator: SurgexCoordinator, outlet_id: str) -> None:
        outlet = coordinator.data.outlet(outlet_id)
        super().__init__(coordinator, f"{outlet.slug}_reboot")
        self._outlet_id = outlet_id
        self._attr_name = f"{outlet.name} reboot"
        if outlet.hidden:
            self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        outlet = self.status.outlet(self._outlet_id)
        if outlet is None:
            raise HomeAssistantError(
                f"Outlet {self._outlet_id} is no longer reported by the device"
            )
        await self.coordinator.client.reboot(outlet.control_path)
        await self.coordinator.async_request_refresh()


class SurgexResetEnergyButton(SurgexEntity, ButtonEntity):
    """Zeroes the cumulative energy counter."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "reset_energy"

    def __init__(self, coordinator: SurgexCoordinator) -> None:
        super().__init__(coordinator, "reset_energy")

    async def async_press(self) -> None:
        await self.coordinator.client.reset_energy(self.status.device_path)
        await self.coordinator.async_request_refresh()
