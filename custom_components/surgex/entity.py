"""Base entity for the SurgeX integration."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SurgexAuthError, SurgexError
from .const import DOMAIN, MANUFACTURER
from .coordinator import SurgexCoordinator
from .models import SquidStatus


class SurgexEntity(CoordinatorEntity[SurgexCoordinator]):
    """Common device identity and availability for every SurgeX entity."""

    _attr_has_entity_name = True

    @contextmanager
    def command(self, operation: str, target: str) -> Iterator[None]:
        """Translate client errors raised by a user-initiated command.

        `SurgexError` and its subclasses are not `HomeAssistantError`, so
        without this a device that dropped off the network between the last
        poll and the user's tap produces an unhandled traceback instead of a
        readable failure in the frontend. Rejected credentials additionally
        start reauth straight away rather than waiting up to a full poll
        interval for the coordinator to notice.
        """
        try:
            yield
        except SurgexAuthError as err:
            if self.coordinator.config_entry is not None:
                self.coordinator.config_entry.async_start_reauth(self.hass)
            raise ConfigEntryAuthFailed(
                f"The device rejected the stored credentials while trying to "
                f"{operation} {target}: {err}"
            ) from err
        except SurgexError as err:
            raise HomeAssistantError(
                f"Failed to {operation} {target}: {err}"
            ) from err

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
