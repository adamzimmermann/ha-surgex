"""Async HTTP client for the SurgeX Squid v1 REST API.

Deliberately free of Home Assistant imports so it can be extracted into a
standalone package. See the Squid v1 REST API Definition (AMETEK), plus the
Live Firmware Findings in the design spec.
"""

from __future__ import annotations

import asyncio
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
        self._auth = aiohttp.BasicAuth(username, password)

    @property
    def base_url(self) -> str:
        scheme = "https" if self._use_https else "http"
        default_port = 443 if self._use_https else 80
        host = self._host if self._port == default_port else f"{self._host}:{self._port}"
        return f"{scheme}://{host}"

    async def _request(
        self, method: str, path: str, *, authenticated: bool = True
    ) -> Any:
        url = f"{self.base_url}/api/v1/{path}"
        kwargs: dict[str, Any] = {"timeout": TIMEOUT}
        if authenticated:
            kwargs["auth"] = self._auth
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
            raise SurgexConnectionError(f"Could not reach {url}: {err}") from err

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
