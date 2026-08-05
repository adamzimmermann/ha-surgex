"""Config flow for the SurgeX integration."""

from __future__ import annotations

from typing import Any, Mapping

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import SurgexAuthError, SurgexClient, SurgexConnectionError, SurgexError
from .const import CONF_USE_HTTPS, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DOMAIN
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

STEP_CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME, default="admin"): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


def _use_https_from_property(value: Any) -> bool:
    """Interpret the `ssl` TXT property, which arrives as a string."""
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().lower() == "true"


class SurgexConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SurgeX."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT
        self._discovered_use_https: bool = False

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

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a device found via _ametekhttp._tcp.local.

        Identity comes from the announcement's TXT properties (`mac`, `type`),
        not a live probe: a Squid identifies itself with no auth needed
        either way, but reading it here means dedup/host-update happens
        before any credentials are on hand to probe with.
        `async_step_discovery_confirm` still runs the full `_probe` once the
        user supplies credentials, so a stale/misleading announcement is
        still caught before an entry is created.

        The TXT properties are a machine interface the device commits to
        (`serial=`, `mac=AA:BB:CC:00:11:22`, `ssl=False`, `version=...`,
        `type=squid`), unlike the cosmetic display name — so identity is read
        from there, not parsed out of `discovery_info.name`.
        """
        host = str(discovery_info.ip_address)
        properties = discovery_info.properties

        mac = properties.get("mac")
        if not mac or str(properties.get("type", "")).lower() != "squid":
            return self.async_abort(reason="not_a_squid")

        await self.async_set_unique_id(normalise_mac(mac))
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._discovered_host = host
        self._discovered_port = discovery_info.port or DEFAULT_PORT
        self._discovered_use_https = _use_https_from_property(properties.get("ssl"))
        self.context["title_placeholders"] = {"name": "SurgeX Squid"}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect credentials for a discovered device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {
                CONF_HOST: self._discovered_host,
                CONF_PORT: self._discovered_port,
                CONF_USE_HTTPS: self._discovered_use_https,
                **user_input,
            }
            try:
                _, model = await self._probe(data)
            except NotASquidError:
                errors["base"] = "not_a_squid"
            except SurgexAuthError:
                errors["base"] = "invalid_auth"
            except SurgexConnectionError:
                errors["base"] = "cannot_connect"
            except SurgexError:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=model, data=data)

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=STEP_CREDENTIALS_SCHEMA,
            errors=errors,
            description_placeholders={"host": self._discovered_host or ""},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after the device rejected stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect replacement credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                await self._probe(data)
            except NotASquidError:
                errors["base"] = "not_a_squid"
            except SurgexAuthError:
                errors["base"] = "invalid_auth"
            except SurgexConnectionError:
                errors["base"] = "cannot_connect"
            except SurgexError:
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_CREDENTIALS_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SurgexOptionsFlow:
        return SurgexOptionsFlow()


class SurgexOptionsFlow(OptionsFlow):
    """Let the user tune how often the device is polled."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                        int, vol.Range(min=5, max=600)
                    )
                }
            ),
        )


class NotASquidError(Exception):
    """The host responded but is not a SurgeX device."""
