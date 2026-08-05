#!/usr/bin/env python3
"""Exercise the integration's client against the real device.

This is the check mocked unit tests cannot do: it talks to an actual SurgeX
Squid PDU and confirms identity, parsing, credential rejection, and control.

It powers one outlet off and back on, restoring whatever state it found. It
writes no device settings and destroys no data: the ResetEnergyUsage check
skips itself unless the energy counter is already at zero. Even so, do not run
it against hardware powering anything you care about.

This script is for checks that stay useful. One-off investigations that have
since been answered -- whether ResetEnergyUsage is device-scoped, whether
temperatureUnits changes the payload -- have been removed rather than left to
re-run forever: both wrote to the device, and the unscoped ResetEnergyUsage
probe hung its HTTP server hard enough to 503 every request for eight minutes.
Their answers live in api.py and models.py.

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

from custom_components.surgex.api import (
    SurgexAuthError,
    SurgexClient,
    SurgexConnectionError,
)
from custom_components.surgex.models import SquidStatus, parse_current_status

# How long to wait after a command before reading the result back. The device
# does not apply commands instantly, so a read taken too soon returns the
# pre-command state and the check fails against working hardware. This is the
# same settle time const.REQUEST_REFRESH_COOLDOWN uses, for the same reason.
# Tests set it to 0; nothing else should change it.
SETTLE_SECONDS = 3


async def check_rejected_password(
    session: aiohttp.ClientSession, host: str, user: str, password: str
) -> None:
    """Confirm a bad password still reads as SurgexAuthError on real firmware.

    This firmware answers a rejected password with a 401 that strict HTTP
    parsers throw out, so api.py infers the rejection by probing the
    unauthenticated WhoAreYou endpoint. Get that wrong -- or send a malformed
    Authorization header -- and the failure degrades into SurgexConnectionError:
    Home Assistant then marks the device unavailable forever instead of
    prompting for reauth.

    Unit tests cover this against a fake device, but only real firmware can
    confirm the malformed reply still looks the way it did when that code was
    written. Read-only: one rejected request and one unauthenticated probe,
    changing nothing on the device.
    """
    print("\nChecking that a rejected password is recognised as an auth failure")
    client = SurgexClient(session, host, user, password + "-wrong")
    try:
        await client.current_status()
    except SurgexAuthError as err:
        print(f"  wrong password: SurgexAuthError (correct) -- {err}")
    except SurgexConnectionError as err:
        raise AssertionError(
            f"Wrong password surfaced as SurgexConnectionError, so Home "
            f"Assistant would never prompt for reauth: {err}"
        ) from err
    else:
        raise AssertionError("The device accepted a deliberately wrong password")


async def check_reset_energy(client: SurgexClient, status: SquidStatus) -> None:
    """Exercise ResetEnergyUsage, but only when there is nothing to lose.

    The command zeroes a counter the API offers no way to restore, and that
    total is real data -- it feeds the Home Assistant Energy dashboard. So the
    reset runs only while the counter already reads 0, and skips itself the
    moment there is anything on it worth keeping.

    Success is judged by energyUsageTime advancing, not by the value: a counter
    reading 0 before and 0 after proves nothing on its own, so the timestamp is
    the only evidence the device acted on the command at all.

    Only the device-scoped path is exercised. The unscoped `/ResetEnergyUsage`
    was probed here to settle which one the firmware wants; it does not merely
    fail, it hangs the connection, and repeated runs exhausted the device's
    HTTP server until it answered 503 to everything for eight minutes. That
    question is settled and the answer lives in api.py: it is device-scoped.
    """
    print("\nChecking ResetEnergyUsage (device-scoped)")

    energy = status.measurements.energy_wh
    if energy is None:
        print("  skipped: this device does not report energyUsage.")
        return
    if energy != 0:
        print(
            f"  SKIPPED: energyUsage reads {energy} Wh and a reset would "
            f"destroy it. This check only runs against a counter already at 0."
        )
        return

    stamp_before = status.measurements.energy_reset
    await client.reset_energy(status.device_path)
    await asyncio.sleep(SETTLE_SECONDS)
    after = parse_current_status(await client.current_status()).measurements

    print(f"  energyUsage     : {after.energy_wh} Wh (was {energy})")
    print(f"  energyUsageTime : {after.energy_reset} (was {stamp_before})")
    assert after.energy_reset != stamp_before, (
        f"ResetEnergyUsage reported success but energyUsageTime did not move "
        f"({stamp_before!r}), so there is no evidence the device acted on it"
    )
    print("  ACCEPTED: the device recorded a fresh reset timestamp.")


async def main(host: str) -> int:
    user = os.environ["SURGEX_USER"]
    password = os.environ["SURGEX_PASS"]

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

        # Read-only, so it runs before anything touches the hardware: a broken
        # credential path should fail the check before an outlet is toggled.
        await check_rejected_password(session, host, user, password)

        # Round-trip a safe outlet. Nothing is plugged in on this unit today,
        # but the script must not assume that -- it snapshots whatever state
        # the outlet is actually in and restores it in a finally block, so an
        # assertion failure partway through cannot leave an outlet off.
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
            await asyncio.sleep(SETTLE_SECONDS)
            after_on = parse_current_status(await client.current_status()).outlet(
                target.id
            )
            print(f"  after PowerOn : state={after_on.state} is_on={after_on.is_on}")
            assert after_on.is_on, "PowerOn did not take effect"

            await client.power_off(target.control_path)
            await asyncio.sleep(SETTLE_SECONDS)
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
            await asyncio.sleep(SETTLE_SECONDS)
            restored = parse_current_status(await client.current_status()).outlet(
                target.id
            )
            print(
                f"  restored      : state={restored.state} is_on={restored.is_on} "
                f"(expected is_on={original_is_on})"
            )

        # Guards itself against wiping a counter that has real data on it.
        await check_reset_energy(client, status)

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
