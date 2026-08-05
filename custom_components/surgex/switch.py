"""Outlet switches for the SurgeX integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
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
        # Set between a successful command and the poll that confirms it; see
        # async_turn_on. None means "trust the coordinator".
        self._optimistic_is_on: bool | None = None
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
        if self._optimistic_is_on is not None:
            return self._optimistic_is_on
        outlet = self._outlet
        return outlet.is_on if outlet else None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Fresh data supersedes the optimistic value."""
        self._optimistic_is_on = None
        super()._handle_coordinator_update()

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

    async def _async_set(self, is_on: bool) -> None:
        """Send a power command, then show the result before it is confirmed.

        The device takes a moment to apply the command, so the confirming poll
        is deferred by the coordinator's debouncer. In the meantime the entity
        shows the state the user asked for; without that it would read back
        the pre-command value and look broken.
        """
        outlet = self._require_outlet()
        operation = "turn on" if is_on else "turn off"
        client = self.coordinator.client
        with self.command(operation, outlet.id):
            if is_on:
                await client.power_on(outlet.control_path)
            else:
                await client.power_off(outlet.control_path)

        self._optimistic_is_on = is_on
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)
