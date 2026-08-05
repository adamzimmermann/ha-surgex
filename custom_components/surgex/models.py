"""Normalisation of SurgeX Squid API payloads into typed objects.

This module absorbs every difference between firmware generations so that no
other module needs to know about them. It must stay free of Home Assistant and
aiohttp imports: it is pure data transformation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

__all__ = [
    "SquidMeasurements",
    "SquidOutlet",
    "SquidStatus",
    "SurgexParseError",
    "normalise_mac",
    "parse_current_status",
]


class SurgexParseError(Exception):
    """Raised when a payload cannot be understood."""


def normalise_mac(value: str) -> str:
    """Return a MAC address as lowercase hex with separators stripped."""
    return value.replace(":", "").replace("-", "").lower()


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _as_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True)
class SquidOutlet:
    """A single switchable output on the device."""

    id: str
    name: str
    physical_name: str
    state: int
    voltage_type: str
    config_voltage: float | None
    reboot_time: int
    hidden: bool

    @property
    def is_on(self) -> bool:
        """True only when powered. State 2 means rebooting, which is not on."""
        return self.state == 1

    @property
    def control_path(self) -> str:
        """The id in the form the control endpoints expect, e.g. '1/3'."""
        return self.id.lstrip("/")

    @property
    def slug(self) -> str:
        """A unique-id-safe form of the outlet id, e.g. '1_3'."""
        return self.id.strip("/").replace("/", "_")


@dataclass(frozen=True)
class SquidMeasurements:
    """Whole-unit electrical measurements. The Squid has no per-outlet metering."""

    power: float | None
    current: float | None
    voltage: float | None
    energy_wh: float | None
    energy_reset: datetime | None
    temperature_c: float | None
    frequency: float | None
    power_factor: float | None
    surge_good: bool | None


@dataclass(frozen=True)
class SquidStatus:
    """A fully parsed snapshot of the device."""

    model: str
    serial: str | None
    mac: str
    firmware: str | None
    hostname: str | None
    outlets: tuple[SquidOutlet, ...]
    measurements: SquidMeasurements
    input_state: str | None
    wiring_fault: bool | None
    device_path: str

    @property
    def unique_id(self) -> str:
        return normalise_mac(self.mac)

    def outlet(self, outlet_id: str) -> SquidOutlet | None:
        return next((o for o in self.outlets if o.id == outlet_id), None)


def _parse_input_state(raw: Any) -> str | None:
    """Normalise inputState, which varies by firmware.

    Firmware 1.01 reports an integer on the device object (0 when healthy) and
    sometimes omits it entirely. The 0.5.x docs describe an array of strings
    inside deviceMeasurements.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return "OK" if raw == 0 else str(raw)
    if isinstance(raw, (list, tuple)):
        return ", ".join(str(item) for item in raw) if raw else "OK"
    if isinstance(raw, str):
        return raw or "OK"
    return None


def _as_int(value: Any, field: str, outlet_id: str) -> int:
    """Coerce a numeric outlet field, reporting failure as a parse error.

    A bare int() raises ValueError or TypeError, neither of which the
    coordinator recognises as a parse failure -- so one malformed outlet would
    produce a full traceback on every poll instead of a single logged message.
    """
    if value is None or value == "":  # absent, null, or blank
        return 0
    if isinstance(value, (int, float)):  # bool included: True reads as 1
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as err:
            raise SurgexParseError(
                f"Outlet {outlet_id} has a non-numeric {field}: {value!r}"
            ) from err
    raise SurgexParseError(
        f"Outlet {outlet_id} has a non-numeric {field}: {value!r}"
    )


def _parse_outlet(raw: Any) -> SquidOutlet:
    if not isinstance(raw, dict):
        raise SurgexParseError(f"Outlet entry is not an object: {raw!r}")
    outlet_id = raw.get("id")
    if not outlet_id or not isinstance(outlet_id, str):
        raise SurgexParseError("Outlet is missing an id")
    physical = raw.get("physicalName") or outlet_id
    return SquidOutlet(
        id=outlet_id,
        name=raw.get("name") or physical,
        physical_name=physical,
        state=_as_int(raw.get("state"), "state", outlet_id),
        voltage_type=raw.get("outputVoltageType") or "AC",
        config_voltage=_as_float(raw.get("configVoltage")),
        reboot_time=_as_int(raw.get("rebootTime"), "rebootTime", outlet_id),
        hidden=bool(raw.get("isHidden", False)),
    )


def _parse_measurements(raw: dict[str, Any]) -> SquidMeasurements:
    surge = raw.get("surgeGood")
    return SquidMeasurements(
        power=_as_float(raw.get("power")),
        current=_as_float(raw.get("current")),
        voltage=_as_float(raw.get("voltageLN") or raw.get("line1Line2")),
        energy_wh=_as_float(raw.get("energyUsage")),
        energy_reset=_as_datetime(raw.get("energyUsageTime")),
        # Reported in Celsius regardless of the temperatureUnits field, which
        # this firmware sets to "F" while emitting an obviously Celsius value.
        temperature_c=_as_float(raw.get("temperature")),
        frequency=_as_float(raw.get("frequency")),
        power_factor=_as_float(raw.get("pf")),
        surge_good=surge if isinstance(surge, bool) else None,
    )


def parse_current_status(payload: dict[str, Any]) -> SquidStatus:
    """Turn a raw /api/v1/currentStatus body into a SquidStatus."""
    if not isinstance(payload, dict):
        raise SurgexParseError("Payload is not an object")

    macs = payload.get("MAC") or []
    if not macs or not isinstance(macs, list):
        raise SurgexParseError("Payload has no MAC address")

    devices = payload.get("devices") or []
    if not devices or not isinstance(devices, list):
        raise SurgexParseError("Payload contains no devices")
    device = devices[0]
    if not isinstance(device, dict):
        raise SurgexParseError(f"Device entry is not an object: {device!r}")

    measurements_raw = device.get("deviceMeasurements")
    if not isinstance(measurements_raw, dict):
        measurements_raw = {}

    outlets_raw = device.get("outlets") or []
    if not isinstance(outlets_raw, list):
        raise SurgexParseError(f"Device outlets is not a list: {outlets_raw!r}")

    # inputState lives on the device in 1.01 and in deviceMeasurements in 0.5.x.
    raw_input_state = device.get("inputState")
    if raw_input_state is None:
        raw_input_state = measurements_raw.get("inputState")

    wiring_fault = device.get("wiringFault")

    serial = payload.get("serial") or None

    return SquidStatus(
        model=payload.get("model") or "Squid",
        serial=serial,
        mac=macs[0],
        firmware=payload.get("firmware") or None,
        hostname=payload.get("hostname") or None,
        outlets=tuple(_parse_outlet(o) for o in outlets_raw),
        measurements=_parse_measurements(measurements_raw),
        input_state=_parse_input_state(raw_input_state),
        wiring_fault=wiring_fault if isinstance(wiring_fault, bool) else None,
        device_path=(device.get("id") or "/1").lstrip("/"),
    )
