"""Tests for the SurgeX HTTP client.

These run against a real socket server rather than a mocked aiohttp, so the
client's behaviour is exercised through an actual HTTP parser. See
tests/fake_device.py for why that matters.
"""

import aiohttp
import pytest

from custom_components.surgex.api import (
    SurgexApiError,
    SurgexAuthError,
    SurgexClient,
    SurgexConnectionError,
)

from .fake_device import (
    MALFORMED_401,
    FakeDevice,
    json_response,
    raw_body_response,
    status_response,
)


@pytest.fixture
async def device(socket_enabled):
    """A fake Squid listening on a real port.

    `socket_enabled` lifts the harness-wide ban on real sockets, which is what
    lets these tests exercise a genuine HTTP parser instead of a mock.
    """
    dev = FakeDevice()
    await dev.start()
    yield dev
    await dev.stop()


@pytest.fixture
async def client(device):
    """A client pointed at the fake Squid."""
    async with aiohttp.ClientSession() as session:
        yield SurgexClient(session, device.host, "admin", "secret", port=device.port)


async def test_base_url_default_port():
    async with aiohttp.ClientSession() as session:
        assert SurgexClient(session, "192.168.1.131", "u", "p").base_url == (
            "http://192.168.1.131"
        )


async def test_base_url_https_and_custom_port():
    async with aiohttp.ClientSession() as session:
        client = SurgexClient(session, "10.0.0.5", "u", "p", port=8443, use_https=True)
        assert client.base_url == "https://10.0.0.5:8443"


async def test_who_are_you_returns_payload(client, device, who_are_you):
    device.route("WhoAreYou", json_response(who_are_you))
    assert (await client.who_are_you())["model"] == "SX-DC-8-12-120"


async def test_who_are_you_is_sent_unauthenticated(client, device, who_are_you):
    """The endpoint needs no credentials; that is what makes it a usable probe."""
    device.route("WhoAreYou", json_response(who_are_you))
    await client.who_are_you()
    assert "authorization" not in device.requests[0].headers


async def test_current_status_returns_payload(client, device, status_1_01):
    device.route("currentStatus", json_response(status_1_01))
    assert (await client.current_status())["model"] == "SX-DC-8-12-120"


async def test_current_status_is_authenticated(client, device, status_1_01):
    device.route("currentStatus", json_response(status_1_01))
    await client.current_status()
    assert device.requests[0].headers["authorization"].startswith("Basic ")


async def test_401_raises_auth_error(client, device):
    device.route("currentStatus", status_response(401, "Unauthorized"))
    with pytest.raises(SurgexAuthError):
        await client.current_status()


async def test_malformed_401_still_raises_auth_error(client, device, who_are_you):
    """Squid answers a bad password with a 401 that strict parsers reject.

    Without special handling the rejected password looks like a network outage,
    so Home Assistant never prompts for reauth and the entities simply go
    unavailable forever.
    """
    device.route("currentStatus", MALFORMED_401)
    device.route("WhoAreYou", json_response(who_are_you))

    with pytest.raises(SurgexAuthError):
        await client.current_status()

    # It must have consulted the unauthenticated endpoint to reach that verdict.
    assert "WhoAreYou" in device.paths_requested


async def test_malformed_response_with_dead_device_is_a_connection_error(
    client, device
):
    """Same broken reply, but the device does not answer WhoAreYou either.

    Nothing then distinguishes this from the device being down, so it must not
    be reported as a credential problem.
    """
    device.route("currentStatus", MALFORMED_401)
    # WhoAreYou intentionally unrouted -> 404 -> SurgexApiError -> unreachable

    with pytest.raises(SurgexConnectionError):
        await client.current_status()


async def test_auth_probe_does_not_recurse(client, device):
    """A broken WhoAreYou must not send the client probing itself forever."""
    device.route("WhoAreYou", MALFORMED_401)
    with pytest.raises(SurgexConnectionError):
        await client.who_are_you()
    assert device.paths_requested.count("WhoAreYou") == 1


async def test_500_raises_api_error(client, device):
    device.route("currentStatus", status_response(500, "Server Error"))
    with pytest.raises(SurgexApiError):
        await client.current_status()


async def test_unreachable_host_raises_connection_error(socket_enabled):
    """Port 1 on localhost refuses connections."""
    async with aiohttp.ClientSession() as session:
        client = SurgexClient(session, "127.0.0.1", "admin", "secret", port=1)
        with pytest.raises(SurgexConnectionError):
            await client.current_status()


async def test_invalid_json_raises_api_error(client, device):
    device.route("currentStatus", raw_body_response("not json"))
    with pytest.raises(SurgexApiError):
        await client.current_status()


async def test_non_object_payload_raises_api_error(client, device):
    device.route("currentStatus", json_response([1, 2, 3]))
    with pytest.raises(SurgexApiError):
        await client.current_status()


@pytest.mark.parametrize(
    ("call", "expected_path"),
    [
        ("power_on", "1/3/PowerOn"),
        ("power_off", "1/3/PowerOff"),
        ("reboot", "1/3/Reboot"),
    ],
)
async def test_outlet_commands_post_to_the_right_path(
    client, device, call, expected_path
):
    device.route(expected_path, json_response(True))
    await getattr(client, call)("1/3")
    request = device.requests[0]
    assert request.method == "POST"
    assert request.path == expected_path


async def test_reset_energy_posts_to_device_path(client, device):
    device.route("1/ResetEnergyUsage", json_response(True))
    await client.reset_energy("1")
    assert device.requests[0].path == "1/ResetEnergyUsage"


async def test_command_returning_false_raises(client, device):
    """A command that is not accepted must surface, not silently no-op."""
    device.route("1/3/PowerOn", json_response(False))
    with pytest.raises(SurgexApiError):
        await client.power_on("1/3")
