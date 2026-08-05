"""Async HTTP client for the SurgeX Squid v1 REST API.

Deliberately free of Home Assistant imports so it can be extracted into a
standalone package. See the Squid v1 REST API Definition (AMETEK), plus the
Live Firmware Findings in the design spec.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import aiohttp

__all__ = [
    "SurgexApiError",
    "SurgexAuthError",
    "SurgexClient",
    "SurgexConnectionError",
    "SurgexError",
]

TIMEOUT = aiohttp.ClientTimeout(total=15)


class SurgexError(Exception):
    """Base class for all client errors."""


class SurgexAuthError(SurgexError):
    """Credentials were rejected."""


class SurgexConnectionError(SurgexError):
    """The device could not be reached."""


class SurgexApiError(SurgexError):
    """The device responded, but not in a usable way."""


class SurgexClient:
    """Talks to one Squid device."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
        port: int = 80,
        use_https: bool = False,
    ) -> None:
        self._session = session
        self._host = host
        self._port = port
        self._use_https = use_https
        # Built once, by hand, and deliberately not with any aiohttp helper.
        # aiohttp.BasicAuth and the request `auth` parameter are removed in
        # aiohttp 4.0, but their replacement -- aiohttp.encode_basic_auth --
        # only exists from aiohttp 3.14, which Home Assistant did not ship
        # until 2026.7. Calling it raises AttributeError on every release from
        # this integration's declared floor (2026.2) through 2026.6, taking
        # the whole integration down at setup.
        #
        # Basic auth is base64 of "user:password" (RFC 7617) and nothing more,
        # so encoding it directly works identically on every aiohttp version
        # and needs no feature detection. UTF-8 matches what
        # aiohttp.encode_basic_auth does.
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._auth_headers = {"Authorization": f"Basic {credentials}"}

    @property
    def base_url(self) -> str:
        scheme = "https" if self._use_https else "http"
        default_port = 443 if self._use_https else 80
        host = self._host if self._port == default_port else f"{self._host}:{self._port}"
        return f"{scheme}://{host}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        probe_auth: bool = True,
    ) -> Any:
        url = f"{self.base_url}/api/v1/{path}"
        kwargs: dict[str, Any] = {"timeout": TIMEOUT}
        if authenticated:
            kwargs["headers"] = self._auth_headers
        if method == "POST":
            kwargs["json"] = []

        try:
            async with self._session.request(method, url, **kwargs) as response:
                if response.status == 401:
                    raise SurgexAuthError("Credentials rejected by the device")
                if response.status >= 400:
                    raise SurgexApiError(
                        f"{method} {path} returned HTTP {response.status}"
                    )
                try:
                    return await response.json(content_type=None)
                except ValueError as err:
                    raise SurgexApiError(f"{path} returned invalid JSON") from err
        except asyncio.TimeoutError as err:
            raise SurgexConnectionError(f"Timed out contacting {url}") from err
        except aiohttp.ClientError as err:
            # Squid firmware sends a malformed 401: it declares Content-Length: 0
            # and then writes a stray "0" body anyway. Strict HTTP parsers reject
            # the whole response, so the 401 status is never visible here and a
            # rejected password would otherwise look like a network outage --
            # leaving entities unavailable instead of prompting for reauth.
            #
            # Disambiguate by asking the device who it is. WhoAreYou needs no
            # credentials, so if it answers, the device is reachable and healthy
            # and the only thing wrong with the failed request was the password.
            if authenticated and probe_auth and await self._reachable():
                raise SurgexAuthError(
                    "Credentials rejected by the device (malformed 401 response)"
                ) from err
            raise SurgexConnectionError(f"Could not reach {url}: {err}") from err

    async def _reachable(self) -> bool:
        """Whether the device answers its unauthenticated identity endpoint."""
        try:
            await self._request(
                "GET", "WhoAreYou", authenticated=False, probe_auth=False
            )
        except SurgexError:
            return False
        return True

    async def _command(self, path: str) -> None:
        """Run a control command, which must return the JSON literal true."""
        result = await self._request("POST", path)
        if result is not True:
            raise SurgexApiError(f"Command {path} was not accepted (returned {result!r})")

    async def who_are_you(self) -> dict[str, Any]:
        """Identity probe. This endpoint requires no authentication."""
        result = await self._request("GET", "WhoAreYou", authenticated=False)
        if not isinstance(result, dict):
            raise SurgexApiError("WhoAreYou did not return an object")
        return result

    async def current_status(self) -> dict[str, Any]:
        result = await self._request("GET", "currentStatus")
        if not isinstance(result, dict):
            raise SurgexApiError("currentStatus did not return an object")
        return result

    async def power_on(self, control_path: str) -> None:
        await self._command(f"{control_path}/PowerOn")

    async def power_off(self, control_path: str) -> None:
        await self._command(f"{control_path}/PowerOff")

    async def reboot(self, control_path: str) -> None:
        await self._command(f"{control_path}/Reboot")

    async def reset_energy(self, device_path: str) -> None:
        await self._command(f"{device_path}/ResetEnergyUsage")
