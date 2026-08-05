"""Polling coordinator for the SurgeX integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    SurgexApiError,
    SurgexAuthError,
    SurgexClient,
    SurgexConnectionError,
)
from .const import CONF_USE_HTTPS, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DOMAIN
from .models import SquidStatus, SurgexParseError, parse_current_status

_LOGGER = logging.getLogger(__name__)

type SurgexConfigEntry = ConfigEntry[SurgexCoordinator]


class SurgexCoordinator(DataUpdateCoordinator[SquidStatus]):
    """Polls currentStatus and feeds every entity from one request."""

    def __init__(
        self, hass: HomeAssistant, entry: SurgexConfigEntry, client: SurgexClient
    ) -> None:
        self.client = client
        self._logged_parse_error = False
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
        )

    async def _async_update_data(self) -> SquidStatus:
        try:
            payload = await self.client.current_status()
        except SurgexAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (SurgexConnectionError, SurgexApiError) as err:
            raise UpdateFailed(str(err)) from err

        try:
            status = parse_current_status(payload)
        except SurgexParseError as err:
            # Log once rather than on every poll cycle.
            if not self._logged_parse_error:
                _LOGGER.error("Could not understand the device payload: %s", err)
                self._logged_parse_error = True
            raise UpdateFailed(str(err)) from err

        self._logged_parse_error = False
        return status


def build_client(hass: HomeAssistant, entry: SurgexConfigEntry) -> SurgexClient:
    """Create a client from a config entry."""
    return SurgexClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        use_https=entry.data.get(CONF_USE_HTTPS, False),
    )
