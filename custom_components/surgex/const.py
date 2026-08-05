"""Constants for the SurgeX integration."""

from homeassistant.const import Platform

DOMAIN = "surgex"
MANUFACTURER = "SurgeX"

DEFAULT_PORT = 80
DEFAULT_SCAN_INTERVAL = 30
CONF_USE_HTTPS = "use_https"

# Platforms are added by the task that creates each one, so every task stays
# independently testable: SWITCH in Task 8, SENSOR in Task 9, BUTTON in
# Task 10, BINARY_SENSOR in Task 11. Task 11 leaves all four here.
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]
