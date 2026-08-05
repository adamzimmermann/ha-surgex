"""Diagnostics support for the SurgeX integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import SurgexConfigEntry

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SurgexConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    status = entry.runtime_data.data
    measurements = status.measurements
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "status": {
            # status.mac is deliberately omitted: it is device-identifying
            # and the config entry's unique_id (derived from it) is already
            # implied elsewhere. Do not add it back.
            "model": status.model,
            "firmware": status.firmware,
            "has_serial": status.serial is not None,
            "outlet_count": len(status.outlets),
            "hidden_outlets": [o.id for o in status.outlets if o.hidden],
            "input_state": status.input_state,
            "wiring_fault": status.wiring_fault,
            "measurements": {
                "power": measurements.power,
                "current": measurements.current,
                "voltage": measurements.voltage,
                "energy_wh": measurements.energy_wh,
                "energy_reset": (
                    measurements.energy_reset.isoformat()
                    if measurements.energy_reset is not None
                    else None
                ),
                "temperature_c": measurements.temperature_c,
                "frequency": measurements.frequency,
                "power_factor": measurements.power_factor,
                "surge_good": measurements.surge_good,
            },
            "outlets": [
                {
                    "id": o.id,
                    "name": o.name,
                    "physical_name": o.physical_name,
                    "state": o.state,
                    "voltage_type": o.voltage_type,
                    "config_voltage": o.config_voltage,
                }
                for o in status.outlets
            ],
        },
    }
