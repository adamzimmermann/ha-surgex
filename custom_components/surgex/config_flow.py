"""Config flow for the SurgeX integration.

This is a minimal placeholder. Home Assistant 2026.2.3 requires an
importable config_flow module for any domain before it will set up that
domain's config entries at all -- even entries created directly (e.g. via
MockConfigEntry in tests) rather than through the UI. Without this file,
`hass.config_entries.async_setup()` fails immediately with SETUP_ERROR and
never reaches `async_setup_entry`, regardless of the manifest's
`config_flow` value. Task 5 replaces this with the real manual-setup flow
(host/port/credentials form, `WhoAreYou` validation, unique-id dedup).
"""

from __future__ import annotations

from typing import Any, Mapping

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class SurgexConfigFlow(ConfigFlow, domain=DOMAIN):
    """Placeholder handler; Task 5 implements the real steps."""

    VERSION = 1

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Placeholder reauth entry point.

        A `ConfigEntryAuthFailed` from the coordinator makes Home Assistant
        start a reauth flow as a background task, which would otherwise
        crash with `UnknownStep` since this flow defines no such step yet.
        Task 6 replaces this with the real reauth confirmation UI.
        """
        return self.async_abort(reason="reauth_not_implemented")
