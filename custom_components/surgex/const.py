"""Constants for the SurgeX integration."""

from homeassistant.const import Platform

DOMAIN = "surgex"
MANUFACTURER = "SurgeX"

DEFAULT_PORT = 80
DEFAULT_SCAN_INTERVAL = 30
CONF_USE_HTTPS = "use_https"

# How long to wait after a control command before the confirming poll runs.
# The device does not apply PowerOn/PowerOff/Reboot instantly: polling it
# immediately returns the pre-command state and would overwrite the entity's
# optimistic value with stale data. Three seconds is the settle time the live
# hardware check uses between a command and its read-back.
REQUEST_REFRESH_COOLDOWN = 3.0

# The platforms this integration sets up for every config entry.
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]
