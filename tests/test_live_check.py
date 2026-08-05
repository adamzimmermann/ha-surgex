"""Tests for scripts/live_check.py.

The script is not part of the shipped integration, but two of its checks carry
real consequences and are worth holding still:

- `check_reset_energy` guards a destructive command. If its guard regresses, a
  routine live check silently wipes an energy total the user was recording,
  and nothing in the API can put it back.
- `check_rejected_password` is the live verification that a bad password stays
  distinguishable from an unreachable device. A version of it that passes no
  matter what the device does would be worse than not having it.

The script lives in scripts/ rather than a package, so it is loaded by path.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import pytest

from custom_components.surgex.models import parse_current_status

from .fake_device import (
    MALFORMED_401,
    FakeDevice,
    json_response,
    status_response,
)

SCRIPT = Path(__file__).parent.parent / "scripts" / "live_check.py"


def _load_live_check():
    spec = importlib.util.spec_from_file_location("live_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["live_check"] = module
    spec.loader.exec_module(module)
    return module


live_check = _load_live_check()


@pytest.fixture(autouse=True)
def no_settle_delay(monkeypatch):
    """Skip the post-command settle wait; nothing here is real hardware."""
    monkeypatch.setattr(live_check, "SETTLE_SECONDS", 0)


def _status(status_1_01, *, energy, stamp="2026-08-05T19:13:29Z"):
    """A parsed snapshot with the energy counter forced to a given state."""
    payload = copy.deepcopy(status_1_01)
    measurements = payload["devices"][0]["deviceMeasurements"]
    measurements["energyUsage"] = energy
    measurements["energyUsageTime"] = stamp
    parsed = parse_current_status(payload)
    if energy is None:
        # The fixture always carries a number, so drop it after parsing to
        # model a device that does not report energyUsage at all.
        parsed = replace(parsed, measurements=replace(parsed.measurements, energy_wh=None))
    return parsed


class StubClient:
    """Records reset_energy calls and replays a canned follow-up status."""

    def __init__(self, after_payload=None):
        self.reset_calls: list[str] = []
        self._after_payload = after_payload

    async def reset_energy(self, device_path: str) -> None:
        self.reset_calls.append(device_path)

    async def current_status(self):
        return self._after_payload


async def test_reset_energy_refuses_to_wipe_a_counter_with_data(status_1_01, capsys):
    """The guard that protects real energy history.

    A device with 1234.5 Wh on the clock has data the user may be recording in
    the Energy dashboard, and ResetEnergyUsage cannot be undone. No API check
    is worth destroying it.
    """
    client = StubClient()
    await live_check.check_reset_energy(client, _status(status_1_01, energy=1234.5))

    assert client.reset_calls == [], "the reset command must not have been sent"
    assert "SKIPPED" in capsys.readouterr().out


async def test_reset_energy_skips_a_device_that_reports_no_energy(status_1_01):
    """Nothing to reset, and nothing the timestamp could prove."""
    client = StubClient()
    await live_check.check_reset_energy(client, _status(status_1_01, energy=None))

    assert client.reset_calls == []


async def test_reset_energy_runs_when_the_counter_is_already_zero(status_1_01, capsys):
    """With nothing to lose the command is sent, and the path is exercised."""
    after = copy.deepcopy(status_1_01)
    after["devices"][0]["deviceMeasurements"].update(
        {"energyUsage": 0.0, "energyUsageTime": "2026-08-05T19:31:45Z"}
    )
    client = StubClient(after)

    await live_check.check_reset_energy(client, _status(status_1_01, energy=0.0))

    assert client.reset_calls == ["1"], "device-scoped path, not the unscoped one"
    assert "ACCEPTED" in capsys.readouterr().out


async def test_reset_energy_fails_when_the_timestamp_does_not_move(status_1_01):
    """A counter reading 0 before and 0 after is not evidence of anything.

    Only energyUsageTime advancing shows the device acted, so a device that
    accepts the command and does nothing must fail the check rather than pass
    it by looking identical to success.
    """
    unchanged = copy.deepcopy(status_1_01)
    unchanged["devices"][0]["deviceMeasurements"].update(
        {"energyUsage": 0.0, "energyUsageTime": "2026-08-05T19:13:29Z"}
    )
    client = StubClient(unchanged)

    with pytest.raises(AssertionError, match="energyUsageTime did not move"):
        await live_check.check_reset_energy(client, _status(status_1_01, energy=0.0))


async def test_reset_energy_uses_the_reported_device_path(status_1_01):
    """The path comes from the payload, not a hardcoded '1'."""
    payload = copy.deepcopy(status_1_01)
    payload["devices"][0]["id"] = "/9"
    status = _status(payload, energy=0.0)

    after = copy.deepcopy(payload)
    after["devices"][0]["deviceMeasurements"].update(
        {"energyUsage": 0.0, "energyUsageTime": "2026-08-05T19:31:45Z"}
    )
    client = StubClient(after)

    await live_check.check_reset_energy(client, status)
    assert client.reset_calls == ["9"]


@pytest.fixture
async def device(socket_enabled):
    dev = FakeDevice()
    await dev.start()
    yield dev
    await dev.stop()


@pytest.fixture
def host(device):
    """Address in the form the script's client accepts.

    SurgexClient renders base_url as scheme://host when the port is the
    default, so a host carrying its own ':port' reaches the fake device
    without the script needing a port parameter it has no use for in the
    field.
    """
    return f"{device.host}:{device.port}"


async def test_rejected_password_check_passes_on_a_malformed_401(
    device, host, who_are_you
):
    """The real firmware behaviour: a 401 strict parsers throw out."""
    device.route("currentStatus", MALFORMED_401)
    device.route("WhoAreYou", json_response(who_are_you))

    async with aiohttp.ClientSession() as session:
        await live_check.check_rejected_password(session, host, "admin", "secret")


async def test_rejected_password_check_passes_on_a_clean_401(device, host):
    device.route("currentStatus", status_response(401, "Unauthorized"))

    async with aiohttp.ClientSession() as session:
        await live_check.check_rejected_password(session, host, "admin", "secret")


async def test_rejected_password_check_fails_if_a_bad_password_is_accepted(
    device, host, status_1_01
):
    """A device that waves through any password must fail the check loudly."""
    device.route("currentStatus", json_response(status_1_01))

    async with aiohttp.ClientSession() as session:
        with pytest.raises(AssertionError, match="accepted a deliberately wrong"):
            await live_check.check_rejected_password(session, host, "admin", "secret")


async def test_rejected_password_check_fails_when_auth_looks_like_an_outage(
    device, host
):
    """The regression this check exists to catch.

    If the device is unreachable -- or the Authorization header is malformed
    enough that api.py cannot tell a rejection from a dead device -- the
    failure surfaces as SurgexConnectionError, Home Assistant never prompts
    for reauth, and the entities go unavailable forever. That must not read
    as a pass.
    """
    await device.stop()

    async with aiohttp.ClientSession() as session:
        with pytest.raises(AssertionError, match="never prompt for reauth"):
            await live_check.check_rejected_password(session, host, "admin", "secret")
