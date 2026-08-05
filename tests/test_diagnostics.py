"""Tests for diagnostics.py."""

import json
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


async def test_diagnostics_includes_measurements(hass, status_1_01):
    """The measurements block is the most support-relevant part of the dump."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="aabbcc001122")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.surgex.coordinator.SurgexClient.current_status",
        return_value=status_1_01,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)

    measurements = result["status"]["measurements"]
    assert measurements["power"] == 0
    assert measurements["current"] == 0.02999
    assert measurements["voltage"] == 122.19999
    assert measurements["energy_wh"] == 0
    assert measurements["energy_reset"] == "2026-08-04T13:01:22+00:00"
    assert measurements["temperature_c"] == 30.79999
    assert measurements["frequency"] == 60.02299
    assert measurements["power_factor"] == 0.03999
    assert measurements["surge_good"] is True

    # Credential redaction must still hold over the enlarged payload.
    assert "secret" not in str(result)

    # And the whole thing must still be JSON-serialisable (datetime is not,
    # unless energy_reset was converted to a string).
    json.dumps(result)


async def test_diagnostics_outlet_includes_name(hass, status_1_01):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="aabbcc001122")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.surgex.coordinator.SurgexClient.current_status",
        return_value=status_1_01,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)
    outlet = result["status"]["outlets"][0]
    assert "name" in outlet
    assert outlet["name"]
