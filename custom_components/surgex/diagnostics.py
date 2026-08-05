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
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "status": {
            "model": status.model,
            "firmware": status.firmware,
            "has_serial": status.serial is not None,
            "outlet_count": len(status.outlets),
            "hidden_outlets": [o.id for o in status.outlets if o.hidden],
            "input_state": status.input_state,
            "wiring_fault": status.wiring_fault,
            "outlets": [
                {
                    "id": o.id,
                    "physical_name": o.physical_name,
                    "state": o.state,
                    "voltage_type": o.voltage_type,
                    "config_voltage": o.config_voltage,
                }
                for o in status.outlets
            ],
        },
    }
