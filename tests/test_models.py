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
    assert m.frequency == 60.188999
    assert m.power_factor == 0.85


def test_device_path_and_hostname(status_1_01, status_0_5):
    live = parse_current_status(status_1_01)
    assert live.hostname == "ametek-AABBCC001122"
    assert live.device_path == "1"

    documented = parse_current_status(status_0_5)
    assert documented.hostname is None
    assert documented.device_path == "1"


def test_boolean_in_numeric_measurement_field_is_not_coerced():
    """bool is a subclass of int in Python; a stray True/False must not become 1.0/0.0."""
    payload = {
        "model": "X", "MAC": ["AA:BB:CC:00:11:22"],
        "devices": [{"id": "/1", "deviceMeasurements": {"power": True}, "outlets": []}],
    }
    assert parse_current_status(payload).measurements.power is None


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


def test_input_state_multi_element_array_joins_with_comma():
    payload = {
        "model": "X", "MAC": ["AA:BB:CC:00:11:22"],
        "devices": [{
            "id": "/1",
            "deviceMeasurements": {"inputState": ["No Ground", "Over Voltage"]},
            "outlets": [],
        }],
    }
    assert parse_current_status(payload).input_state == "No Ground, Over Voltage"


def test_input_state_empty_array_is_ok():
    payload = {
        "model": "X", "MAC": ["AA:BB:CC:00:11:22"],
        "devices": [{"id": "/1", "deviceMeasurements": {"inputState": []}, "outlets": []}],
    }
    assert parse_current_status(payload).input_state == "OK"


def test_wiring_fault_reads_lowercase_key_and_is_none_when_absent():
    """wiringFault is a plain lowercase-first key in both firmware generations."""
    base = {"model": "X", "MAC": ["AA:BB:CC:00:11:22"]}

    true_payload = {**base, "devices": [{"id": "/1", "wiringFault": True, "deviceMeasurements": {}, "outlets": []}]}
    assert parse_current_status(true_payload).wiring_fault is True

    false_payload = {**base, "devices": [{"id": "/1", "wiringFault": False, "deviceMeasurements": {}, "outlets": []}]}
    assert parse_current_status(false_payload).wiring_fault is False

    absent_payload = {**base, "devices": [{"id": "/1", "deviceMeasurements": {}, "outlets": []}]}
    assert parse_current_status(absent_payload).wiring_fault is None


def test_missing_mac_raises():
    with pytest.raises(SurgexParseError):
        parse_current_status({"model": "X", "devices": []})


def test_missing_devices_raises():
    with pytest.raises(SurgexParseError):
        parse_current_status({"model": "X", "MAC": ["AA:BB:CC:00:11:22"]})
