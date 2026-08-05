from unittest.mock import patch

from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorStateClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
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
    entity_id = registry.async_get_entity_id(SENSOR_DOMAIN, DOMAIN, f"{unique_id}_{suffix}")
    assert entity_id, f"no sensor for {suffix}"
    return hass.states.get(entity_id)


async def test_power_sensor(hass, status_0_5):
    await _setup(hass, status_0_5, "0eb33ad5a064")
    state = _state(hass, "power", "0eb33ad5a064")
    assert state.state == "777.0"
    assert state.attributes[ATTR_DEVICE_CLASS] == "power"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfPower.WATT


async def test_current_and_voltage(hass, status_0_5):
    await _setup(hass, status_0_5, "0eb33ad5a064")
    assert _state(hass, "current", "0eb33ad5a064").state == "6.01"
    assert _state(hass, "voltage", "0eb33ad5a064").state == "118.300003"


async def test_energy_sensor_is_total_with_last_reset(hass, status_0_5):
    await _setup(hass, status_0_5, "0eb33ad5a064")
    state = _state(hass, "energy", "0eb33ad5a064")
    assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfEnergy.WATT_HOUR
    assert state.attributes["last_reset"] == "2020-01-07T17:17:27+00:00"


async def test_temperature_is_celsius_despite_units_field(hass, status_1_01):
    """Device says F; the value is Celsius. Publishing 31°F would be wrong."""
    await _setup(hass, status_1_01)
    state = _state(hass, "temperature")
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "°C"
    assert 10 < float(state.state) < 60


async def test_input_state_integer_zero_reads_ok(hass, status_1_01):
    await _setup(hass, status_1_01)
    assert _state(hass, "input_state").state == "OK"


async def test_input_state_array_is_joined(hass, status_0_5):
    await _setup(hass, status_0_5, "0eb33ad5a064")
    assert _state(hass, "input_state", "0eb33ad5a064").state == "No Ground"


async def test_input_state_sensor_absent_when_key_missing(hass, status_1_01):
    """Rather than a permanently unknown entity, create nothing."""
    payload = {**status_1_01}
    payload["devices"] = [{**payload["devices"][0]}]
    payload["devices"][0].pop("inputState", None)
    payload["devices"][0]["deviceMeasurements"] = {
        k: v for k, v in payload["devices"][0]["deviceMeasurements"].items()
        if k != "inputState"
    }
    await _setup(hass, payload)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id(SENSOR_DOMAIN, DOMAIN, "aabbcc001122_input_state") is None
