from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.surgex.const import DOMAIN

ENTRY_DATA = {CONF_HOST: "192.168.1.131", CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}


@pytest.fixture
async def setup_live(hass, status_1_01):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="aabbcc001122")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.surgex.coordinator.SurgexClient.current_status",
        return_value=status_1_01,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _entity_id(hass, suffix):
    registry = er.async_get(hass)
    return registry.async_get_entity_id(BUTTON_DOMAIN, DOMAIN, f"aabbcc001122_{suffix}")


async def test_reboot_button_per_outlet_plus_energy_reset(hass, setup_live):
    buttons = [s for s in hass.states.async_all() if s.entity_id.startswith("button.")]
    assert len(buttons) == 8  # 7 outlets + 1 energy reset


async def test_reboot_button_calls_reboot(hass, setup_live, status_1_01):
    entity_id = _entity_id(hass, "1_3_reboot")
    with (
        patch(
            "custom_components.surgex.coordinator.SurgexClient.reboot",
            new_callable=AsyncMock,
        ) as reboot,
        patch(
            "custom_components.surgex.coordinator.SurgexClient.current_status",
            return_value=status_1_01,
        ),
    ):
        await hass.services.async_call(
            BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        await hass.async_block_till_done()
    reboot.assert_awaited_once_with("1/3")


async def test_energy_reset_button_calls_reset(hass, setup_live, status_1_01):
    entity_id = _entity_id(hass, "reset_energy")
    with (
        patch(
            "custom_components.surgex.coordinator.SurgexClient.reset_energy",
            new_callable=AsyncMock,
        ) as reset,
        patch(
            "custom_components.surgex.coordinator.SurgexClient.current_status",
            return_value=status_1_01,
        ),
    ):
        await hass.services.async_call(
            BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        await hass.async_block_till_done()
    reset.assert_awaited_once_with("1")
