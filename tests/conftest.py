"""Shared pytest fixtures for the SurgeX integration tests."""

import json
from pathlib import Path

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


@pytest.fixture
def status_1_01() -> dict:
    """currentStatus captured from a live SX-DC-8-12-120 on firmware 1.01."""
    return _load("current_status_1_01.json")


@pytest.fixture
def status_0_5() -> dict:
    """currentStatus in the shape AMETEK's 0.5.x documentation describes."""
    return _load("current_status_0_5_documented.json")


@pytest.fixture
def who_are_you() -> dict:
    """WhoAreYou response captured from the live device."""
    return _load("who_are_you.json")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Required by pytest-homeassistant-custom-component to load custom_components."""
    yield


@pytest.fixture
def device_registry(hass):
    from homeassistant.helpers import device_registry as dr

    return dr.async_get(hass)
