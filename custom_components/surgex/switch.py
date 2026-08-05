"""Outlet switches for the SurgeX integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SurgexConfigEntry, SurgexCoordinator
from .entity import SurgexEntity
from .models import SquidOutlet


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurgexConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one switch per outlet the device reports."""
    coordinator = entry.runtime_data
    async_add_entities(
        SurgexOutletSwitch(coordinator, outlet.id) for outlet in coordinator.data.outlets
    )


class SurgexOutletSwitch(SurgexEntity, SwitchEntity):
    """A single switchable outlet or DC bank."""

    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(self, coordinator: SurgexCoordinator, outlet_id: str) -> None:
        outlet = coordinator.data.outlet(outlet_id)
        super().__init__(coordinator, outlet.slug)
        self._outlet_id = outlet_id
        self._attr_name = outlet.name
        if outlet.hidden:
            # Hidden outlets are infrastructure — on this hardware the AC/DC
            # Input feeds both DC banks. Keep it reachable but out of the way.
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def _outlet(self) -> SquidOutlet | None:
        return self.status.outlet(self._outlet_id)

    @property
    def available(self) -> bool:
        return super().available and self._outlet is not None

    @property
    def is_on(self) -> bool | None:
        outlet = self._outlet
        return outlet.is_on if outlet else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        outlet = self._outlet
        if outlet is None:
            return None
        # Exposes 2 == rebooting, which is_on cannot express on its own.
        return {"raw_state": outlet.state, "voltage_type": outlet.voltage_type}

    def _require_outlet(self) -> SquidOutlet:
        """Return the outlet, or fail loudly if the device stopped reporting it."""
        outlet = self._outlet
        if outlet is None:
            raise HomeAssistantError(
                f"Outlet {self._outlet_id} is no longer reported by the device"
            )
        return outlet

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.power_on(self._require_outlet().control_path)
        # Write-through: refresh now rather than waiting for the next poll.
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.power_off(self._require_outlet().control_path)
        await self.coordinator.async_request_refresh()
