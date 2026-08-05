from datetime import datetime, timezone

import pytest

from custom_components.surgex.models import (
    SurgexParseError,
    normalise_mac,
    parse_current_status,
)


def test_normalise_mac_strips_colons_and_lowercases():
    assert normalise_mac("AA:BB:CC:00:11:22") == "aabbcc001122"


def test_parses_live_firmware_payload(status_1_01):
    status = parse_current_status(status_1_01)
    assert status.model == "SX-DC-8-12-120"
    assert status.unique_id == "aabbcc001122"
    assert status.firmware == "1.01.26815"
    assert len(status.outlets) == 7


def test_empty_serial_becomes_none(status_1_01):
    assert parse_current_status(status_1_01).serial is None


def test_documented_payload_keeps_serial(status_0_5):
    assert parse_current_status(status_0_5).serial == "240320200000"


def test_hidden_outlet_flagged(status_1_01):
    status = parse_current_status(status_1_01)
    hidden = [o for o in status.outlets if o.hidden]
    assert len(hidden) == 1
    assert hidden[0].name == "AC/DC Input"


def test_no_hidden_outlets_in_documented_payload(status_0_5):
    assert not any(o.hidden for o in parse_current_status(status_0_5).outlets)


def test_outlet_control_path_and_slug(status_0_5):
    outlet = parse_current_status(status_0_5).outlet("/1/3")
    assert outlet.control_path == "1/3"
    assert outlet.slug == "1_3"


def test_outlet_is_on_only_when_state_is_one(status_0_5):
    status = parse_current_status(status_0_5)
    assert status.outlet("/1/1").is_on is True
    assert status.outlet("/1/3").is_on is False
    # state 2 is "rebooting" — the outlet has no power, so it is not on
    assert status.outlet("/1/4").state == 2
    assert status.outlet("/1/4").is_on is False


def test_dc_bank_voltages_are_model_generic(status_0_5):
    status = parse_current_status(status_0_5)
    assert status.outlet("/1/5").config_voltage == 12
    assert status.outlet("/1/6").config_voltage == 24


def test_measurements_parsed(status_0_5):
    m = parse_current_status(status_0_5).measurements
    assert m.power == 777
    assert m.current == 6.01
    assert m.voltage == 118.300003
    assert m.energy_wh == 1435072
    assert m.surge_good is True
    assert m.energy_reset == datetime(2020, 1, 7, 17, 17, 27, tzinfo=timezone.utc)


def test_temperature_always_celsius_ignoring_units_field(status_1_01):
    # Device reports temperatureUnits "F" but the value is plainly Celsius.
    assert status_1_01["temperatureUnits"] == "F"
    temp = parse_current_status(status_1_01).measurements.temperature_c
    assert 10 < temp < 60


def test_input_state_integer_zero_is_ok(status_1_01):
    assert parse_current_status(status_1_01).input_state == "OK"


def test_input_state_string_array_is_joined(status_0_5):
    assert parse_current_status(status_0_5).input_state == "No Ground"


def test_input_state_absent_is_none():
    payload = {
        "model": "X", "MAC": ["AA:BB:CC:00:11:22"],
        "devices": [{"id": "/1", "deviceMeasurements": {}, "outlets": []}],
    }
    assert parse_current_status(payload).input_state is None


def test_input_state_nonzero_integer_is_reported():
    payload = {
        "model": "X", "MAC": ["AA:BB:CC:00:11:22"],
        "devices": [{"id": "/1", "inputState": 4, "deviceMeasurements": {}, "outlets": []}],
    }
    assert parse_current_status(payload).input_state == "4"


def test_pascalcase_and_lowercase_connected_both_read():
    """Firmware 1.01 uses PascalCase where the docs use lowercase."""
    base = {"model": "X", "MAC": ["AA:BB:CC:00:11:22"]}
    pascal = {**base, "devices": [{"id": "/1", "wiringFault": True, "deviceMeasurements": {}, "outlets": []}]}
    assert parse_current_status(pascal).wiring_fault is True


def test_missing_mac_raises():
    with pytest.raises(SurgexParseError):
        parse_current_status({"model": "X", "devices": []})


def test_missing_devices_raises():
    with pytest.raises(SurgexParseError):
        parse_current_status({"model": "X", "MAC": ["AA:BB:CC:00:11:22"]})
