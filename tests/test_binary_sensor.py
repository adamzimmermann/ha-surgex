from unittest.mock import patch

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.surgex.const import DOMAIN

ENTRY_DATA = {CONF_HOST: "192.168.1.131", CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}


async def _setup(hass, payload, unique_id="aabbcc001122"):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id=unique_id)
    entry.add_to_hass(hass)
    with patch(
        "custom_components.surgex.coordinator.SurgexClient.current_status",
        return_value=payload,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _state(hass, suffix, unique_id="aabbcc001122"):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        BINARY_SENSOR_DOMAIN, DOMAIN, f"{unique_id}_{suffix}"
    )
    return hass.states.get(entity_id) if entity_id else None


async def test_surge_good_means_no_problem(hass, status_1_01):
    """surgeGood true is healthy, so the problem sensor must read off."""
    await _setup(hass, status_1_01)
    state = _state(hass, "surge_protection")
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_DEVICE_CLASS] == "problem"


async def test_blown_surge_fuse_is_a_problem(hass, status_1_01):
    payload = {**status_1_01}
    payload["devices"] = [{**payload["devices"][0]}]
    payload["devices"][0]["deviceMeasurements"] = {
        **payload["devices"][0]["deviceMeasurements"],
        "surgeGood": False,
    }
    await _setup(hass, payload)
    assert _state(hass, "surge_protection").state == STATE_ON


async def test_wiring_fault_sensor_created_when_present(hass, status_1_01):
    await _setup(hass, status_1_01)
    assert _state(hass, "wiring_fault").state == STATE_OFF


async def test_wiring_fault_sensor_absent_when_key_missing(hass, status_0_5):
    """The documented 0.5.x payload has no wiringFault; create nothing."""
    await _setup(hass, status_0_5, "0eb33ad5a064")
    assert _state(hass, "wiring_fault", "0eb33ad5a064") is None
