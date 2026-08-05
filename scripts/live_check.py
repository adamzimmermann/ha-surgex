#!/usr/bin/env python3
"""Exercise the integration's client against the real device.

This is the check that mocked unit tests cannot do: it talks to an actual
SurgeX Squid PDU and confirms identity, parsing, control, and two
documentation ambiguities the design spec flagged.

It toggles a real outlet and briefly changes a device setting, restoring both.
Do not run it against hardware powering anything you care about.

Usage:
    set -a; . ./.secrets.env; set +a
    .venv/bin/python scripts/live_check.py <device-host-or-ip>
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import aiohttp

from custom_components.surgex.api import SurgexApiError, SurgexClient
from custom_components.surgex.models import parse_current_status

TIMEOUT = aiohttp.ClientTimeout(total=15)


async def try_reset_energy(label: str, coro) -> None:
    """Attempt one ResetEnergyUsage path and report accepted/rejected.

    Uses only the client's public API (or, for the unscoped path, a raw
    request built the same way the client builds its own) -- no reaching
    into private methods. A malformed path on this firmware can also hang
    the connection rather than returning a clean HTTP error, so connection
    failures are reported as a distinct outcome rather than crashing.
    """
    try:
        await coro
    except SurgexApiError as err:
        print(f"  {label:14}: rejected ({err})")
    except (asyncio.TimeoutError, aiohttp.ClientError) as err:
        print(f"  {label:14}: no response / connection error ({err!r})")
    else:
        print(f"  {label:14}: ACCEPTED")


async def raw_command(
    session: aiohttp.ClientSession, base_url: str, headers: dict[str, str], path: str
) -> None:
    """POST a control command exactly the way SurgexClient does, without
    going through the client. Needed to probe the unscoped ResetEnergyUsage
    path, which the client's public API has no method for.
    """
    url = f"{base_url}/api/v1/{path}"
    async with session.post(url, json=[], headers=headers, timeout=TIMEOUT) as response:
        if response.status >= 400:
            raise SurgexApiError(f"POST {path} returned HTTP {response.status}")
        result = await response.json(content_type=None)
    if result is not True:
        raise SurgexApiError(f"Command {path} was not accepted (returned {result!r})")


async def get_json(
    session: aiohttp.ClientSession, base_url: str, headers: dict[str, str], path: str
):
    url = f"{base_url}/api/v1/{path}"
    async with session.get(url, headers=headers, timeout=TIMEOUT) as response:
        response.raise_for_status()
        return await response.json(content_type=None)


async def put_json(
    session: aiohttp.ClientSession,
    base_url: str,
    headers: dict[str, str],
    path: str,
    payload,
):
    url = f"{base_url}/api/v1/{path}"
    async with session.put(url, json=payload, headers=headers, timeout=TIMEOUT) as response:
        response.raise_for_status()
        return await response.json(content_type=None)


async def check_temperature_units(
    session: aiohttp.ClientSession, base_url: str, headers: dict[str, str]
) -> None:
    """Determine whether deviceSettings.temperatureUnits affects the
    currentStatus temperature payload.

    api.py deliberately has no deviceSettings methods -- it is read/control
    only -- so this talks to the endpoint directly rather than adding
    settings-writing methods to the client.
    """
    print("\nChecking temperature units")

    settings = await get_json(session, base_url, headers, "deviceSettings")
    original_units = settings.get("temperatureUnits")
    print(f"  deviceSettings.temperatureUnits (before): {original_units!r}")

    # Flip to whichever value the device is *not* already on. Writing 'C' to a
    # device already set to 'C' compares the payload with itself, which reads
    # as "unchanged" and looks like proof while proving nothing.
    known_units = str(original_units).upper() if original_units else None
    probe_units = {"C": "F", "F": "C"}.get(known_units)

    status_before = await get_json(session, base_url, headers, "currentStatus")
    temp_before = status_before["devices"][0]["deviceMeasurements"]["temperature"]
    print(f"  currentStatus temperature (units={original_units!r}): {temp_before}")

    if probe_units is None:
        print(
            f"  VERDICT: inconclusive -- temperatureUnits reads "
            f"{original_units!r}, so there is no opposite value to flip to. "
            f"Device left untouched."
        )
        return

    try:
        await put_json(
            session, base_url, headers, "deviceSettings", {"temperatureUnits": probe_units}
        )
        status_after = await get_json(session, base_url, headers, "currentStatus")
        temp_after = status_after["devices"][0]["deviceMeasurements"]["temperature"]
        print(f"  currentStatus temperature (units={probe_units!r}): {temp_after}")

        if temp_before == temp_after:
            print(
                f"  VERDICT: value unchanged across {known_units} -> "
                f"{probe_units} -- the payload is Celsius regardless of "
                f"temperatureUnits. models.py is already correct."
            )
        else:
            print(
                f"  VERDICT: value changed across {known_units} -> "
                f"{probe_units} -- temperatureUnits is meaningful. "
                f"models.py needs to convert when units are 'F'."
            )
    finally:
        # Leaving the user's device in a changed state is not acceptable.
        # Restore the units that were actually captured, not a hardcoded 'F':
        # a device already set to Celsius must not come back Fahrenheit.
        # Restore unconditionally, even if the check above raised.
        await put_json(
            session,
            base_url,
            headers,
            "deviceSettings",
            {"temperatureUnits": original_units},
        )
        restored = await get_json(session, base_url, headers, "deviceSettings")
        print(
            f"  deviceSettings.temperatureUnits (restored): "
            f"{restored.get('temperatureUnits')!r} (expected {original_units!r})"
        )


async def main(host: str) -> int:
    user = os.environ["SURGEX_USER"]
    password = os.environ["SURGEX_PASS"]
    base_url = f"http://{host}"
    headers = {"Authorization": aiohttp.encode_basic_auth(user, password)}

    print("=" * 72)
    print(f"LIVE DEVICE CHECK against {host} -- THIS TOGGLES REAL HARDWARE.")
    print("It will pick one non-hidden outlet, power it on then off, then")
    print("restore it to whatever state it was in before this script ran.")
    print("=" * 72)

    async with aiohttp.ClientSession() as session:
        client = SurgexClient(session, host, user, password)

        identity = await client.who_are_you()
        print(f"WhoAreYou    : {identity['model']} fw {identity['firmware']}")

        status = parse_current_status(await client.current_status())
        print(f"Parsed       : {status.model} / {len(status.outlets)} outlets")
        print(f"unique_id    : {status.unique_id}")
        print(f"input_state  : {status.input_state}")
        print(f"wiring_fault : {status.wiring_fault}")
        print(f"temperature  : {status.measurements.temperature_c} (treated as C)")
        for outlet in status.outlets:
            flag = " [hidden]" if outlet.hidden else ""
            print(f"  {outlet.id} {outlet.name!r} state={outlet.state}{flag}")

        # Round-trip a safe outlet. Nothing is plugged in on this unit today,
        # but the script must not assume that -- it snapshots whatever state
        # the outlet is actually in and restores it, the same way the
        # temperature-units check restores deviceSettings.
        target = next(o for o in status.outlets if not o.hidden)
        original_is_on = target.is_on
        print(
            f"\nSelected outlet {target.id} ({target.name!r}) for the "
            f"round-trip -- currently {'ON' if original_is_on else 'OFF'}. "
            f"It will be restored to that state when this script exits, "
            f"even if an assertion below fails."
        )

        try:
            await client.power_on(target.control_path)
            await asyncio.sleep(3)
            after_on = parse_current_status(await client.current_status()).outlet(
                target.id
            )
            print(f"  after PowerOn : state={after_on.state} is_on={after_on.is_on}")
            assert after_on.is_on, "PowerOn did not take effect"

            await client.power_off(target.control_path)
            await asyncio.sleep(3)
            after_off = parse_current_status(await client.current_status()).outlet(
                target.id
            )
            print(f"  after PowerOff: state={after_off.state} is_on={after_off.is_on}")
            assert not after_off.is_on, "PowerOff did not take effect"
        finally:
            # Restore unconditionally -- this must run even if an assertion
            # above raised partway through the round-trip.
            if original_is_on:
                await client.power_on(target.control_path)
            else:
                await client.power_off(target.control_path)
            await asyncio.sleep(3)
            restored = parse_current_status(await client.current_status()).outlet(
                target.id
            )
            print(
                f"  restored      : state={restored.state} is_on={restored.is_on} "
                f"(expected is_on={original_is_on})"
            )

        # Resolve the documented ambiguity in the ResetEnergyUsage path.
        # Two explicit, clearly-labelled attempts -- energyUsage currently
        # reads 0, so either outcome is harmless.
        print("\nProbing ResetEnergyUsage paths")
        await try_reset_energy(
            "device-scoped", client.reset_energy(status.device_path)
        )
        await try_reset_energy(
            "unscoped", raw_command(session, base_url, headers, "ResetEnergyUsage")
        )

        # Resolve whether temperatureUnits affects the currentStatus payload.
        await check_temperature_units(session, base_url, headers)

    print("\nLive check passed.")
    return 0


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SURGEX_HOST")
    if not host:
        print(
            "Usage: live_check.py <device-host-or-ip>   (or set SURGEX_HOST)",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(asyncio.run(main(host)))
