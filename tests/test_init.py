from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.surgex.api import SurgexAuthError, SurgexConnectionError
from custom_components.surgex.const import DOMAIN

ENTRY_DATA = {
    CONF_HOST: "192.168.1.131",
    CONF_PORT: 80,
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "secret",
}


def _entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="aabbcc001122")


async def test_setup_entry_loads(hass, status_1_01):
    entry = _entry()
    entry.add_to_hass(hass)
    with patch(
        "custom_components.surgex.coordinator.SurgexClient.current_status",
        return_value=status_1_01,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_setup_entry_retries_on_connection_error(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    with patch(
        "custom_components.surgex.coordinator.SurgexClient.current_status",
        side_effect=SurgexConnectionError("boom"),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_entry_starts_reauth_on_auth_error(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    with patch(
        "custom_components.surgex.coordinator.SurgexClient.current_status",
        side_effect=SurgexAuthError("nope"),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_unload_entry(hass, status_1_01):
    entry = _entry()
    entry.add_to_hass(hass)
    with patch(
        "custom_components.surgex.coordinator.SurgexClient.current_status",
        return_value=status_1_01,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
