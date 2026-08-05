from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.surgex.const import DOMAIN
from custom_components.surgex.entity import SurgexEntity

ENTRY_DATA = {CONF_HOST: "192.168.1.131", CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}


async def _setup(hass, payload):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="aabbcc001122")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.surgex.coordinator.SurgexClient.current_status",
        return_value=payload,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_unique_id_is_mac_prefixed(hass, status_1_01):
    entry = await _setup(hass, status_1_01)
    entity = SurgexEntity(entry.runtime_data, "power")
    assert entity.unique_id == "aabbcc001122_power"


async def test_device_info_carries_identity(hass, status_1_01):
    entry = await _setup(hass, status_1_01)
    info = SurgexEntity(entry.runtime_data, "power").device_info
    assert info["identifiers"] == {(DOMAIN, "aabbcc001122")}
    assert info["model"] == "SX-DC-8-12-120"
    assert info["manufacturer"] == "SurgeX"
    assert info["sw_version"] == "1.01.26815"
    assert info["configuration_url"] == "http://192.168.1.131"


async def test_empty_serial_is_omitted(hass, status_1_01):
    """The live unit reports serial as an empty string — do not show a blank field."""
    entry = await _setup(hass, status_1_01)
    assert "serial_number" not in SurgexEntity(entry.runtime_data, "power").device_info


async def test_serial_included_when_present(hass, status_0_5):
    entry = await _setup(hass, status_0_5)
    info = SurgexEntity(entry.runtime_data, "power").device_info
    assert info["serial_number"] == "240320200000"
