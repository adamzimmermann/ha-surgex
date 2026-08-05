import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.surgex.api import (
    SurgexApiError,
    SurgexAuthError,
    SurgexClient,
    SurgexConnectionError,
)

BASE = "http://192.168.1.131"


@pytest.fixture
async def client():
    async with aiohttp.ClientSession() as session:
        yield SurgexClient(session, "192.168.1.131", "admin", "secret")


async def test_base_url_default_port(client):
    assert client.base_url == "http://192.168.1.131"


async def test_base_url_https_and_custom_port():
    async with aiohttp.ClientSession() as session:
        c = SurgexClient(session, "10.0.0.5", "u", "p", port=8443, use_https=True)
        assert c.base_url == "https://10.0.0.5:8443"


async def test_who_are_you_returns_payload(client, who_are_you):
    with aioresponses() as m:
        m.get(f"{BASE}/api/v1/WhoAreYou", payload=who_are_you)
        assert (await client.who_are_you())["model"] == "SX-DC-8-12-120"


async def test_current_status_returns_payload(client, status_1_01):
    with aioresponses() as m:
        m.get(f"{BASE}/api/v1/currentStatus", payload=status_1_01)
        assert (await client.current_status())["model"] == "SX-DC-8-12-120"


async def test_401_raises_auth_error(client):
    with aioresponses() as m:
        m.get(f"{BASE}/api/v1/currentStatus", status=401)
        with pytest.raises(SurgexAuthError):
            await client.current_status()


async def test_500_raises_api_error(client):
    with aioresponses() as m:
        m.get(f"{BASE}/api/v1/currentStatus", status=500)
        with pytest.raises(SurgexApiError):
            await client.current_status()


async def test_network_failure_raises_connection_error(client):
    with aioresponses() as m:
        m.get(f"{BASE}/api/v1/currentStatus", exception=aiohttp.ClientError())
        with pytest.raises(SurgexConnectionError):
            await client.current_status()


async def test_invalid_json_raises_api_error(client):
    with aioresponses() as m:
        m.get(f"{BASE}/api/v1/currentStatus", body="not json", content_type="text/html")
        with pytest.raises(SurgexApiError):
            await client.current_status()


async def test_power_on_posts_to_correct_path(client):
    with aioresponses() as m:
        m.post(f"{BASE}/api/v1/1/3/PowerOn", body="true", content_type="application/json")
        await client.power_on("1/3")
        assert ("POST", aiohttp.client.URL(f"{BASE}/api/v1/1/3/PowerOn")) in m.requests


async def test_power_off_posts_to_correct_path(client):
    with aioresponses() as m:
        m.post(f"{BASE}/api/v1/1/3/PowerOff", body="true", content_type="application/json")
        await client.power_off("1/3")


async def test_reboot_posts_to_correct_path(client):
    with aioresponses() as m:
        m.post(f"{BASE}/api/v1/1/3/Reboot", body="true", content_type="application/json")
        await client.reboot("1/3")


async def test_reset_energy_posts_to_device_path(client):
    with aioresponses() as m:
        m.post(f"{BASE}/api/v1/1/ResetEnergyUsage", body="true", content_type="application/json")
        await client.reset_energy("1")


async def test_command_returning_false_raises(client):
    """A command that does not return true must surface, not silently no-op."""
    with aioresponses() as m:
        m.post(f"{BASE}/api/v1/1/3/PowerOn", body="false", content_type="application/json")
        with pytest.raises(SurgexApiError):
            await client.power_on("1/3")
