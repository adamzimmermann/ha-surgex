"""Tests for diagnostics.py."""

from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.surgex.const import DOMAIN
from custom_components.surgex.diagnostics import async_get_config_entry_diagnostics

ENTRY_DATA = {CONF_HOST: "192.168.1.131", CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}


async def test_diagnostics_redacts_credentials(hass, status_1_01):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="aabbcc001122")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.surgex.coordinator.SurgexClient.current_status",
        return_value=status_1_01,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)
    blob = str(result)
    assert "secret" not in blob
    assert result["status"]["model"] == "SX-DC-8-12-120"
    assert result["status"]["outlet_count"] == 7
