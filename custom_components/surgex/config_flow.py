"""Config flow for the SurgeX integration."""

from __future__ import annotations

from typing import Any, Mapping

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SurgexAuthError, SurgexClient, SurgexConnectionError, SurgexError
from .const import CONF_USE_HTTPS, DEFAULT_PORT, DOMAIN
from .models import normalise_mac

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME, default="admin"): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_USE_HTTPS, default=False): bool,
    }
)


class SurgexConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SurgeX."""

    VERSION = 1

    async def _probe(self, data: dict[str, Any]) -> tuple[str, str]:
        """Return (mac, model), raising on failure.

        WhoAreYou needs no authentication, so it runs first: it proves a Squid
        is really at this address before credentials are blamed for anything.
        """
        client = SurgexClient(
            async_get_clientsession(self.hass),
            data[CONF_HOST],
            data[CONF_USERNAME],
            data[CONF_PASSWORD],
            port=data.get(CONF_PORT, DEFAULT_PORT),
            use_https=data.get(CONF_USE_HTTPS, False),
        )

        identity = await client.who_are_you()
        macs = identity.get("MAC") or []
        if not macs:
            raise NotASquidError
        # Only now are credentials in question.
        await client.current_status()
        return normalise_mac(macs[0]), identity.get("model") or "Squid"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                mac, model = await self._probe(user_input)
            except NotASquidError:
                errors["base"] = "not_a_squid"
            except SurgexAuthError:
                errors["base"] = "invalid_auth"
            except SurgexConnectionError:
                errors["base"] = "cannot_connect"
            except SurgexError:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                return self.async_create_entry(title=model, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

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


class NotASquidError(Exception):
    """The host responded but is not a SurgeX device."""
