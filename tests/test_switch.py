from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    EntityCategory,
)
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.surgex.api import SurgexAuthError, SurgexConnectionError
from custom_components.surgex.const import DOMAIN, REQUEST_REFRESH_COOLDOWN

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


async def test_creates_a_switch_per_outlet(hass, setup_live):
    switches = [s for s in hass.states.async_all() if s.entity_id.startswith("switch.")]
    assert len(switches) == 7


async def test_switch_state_reflects_payload(hass, setup_live):
    registry = er.async_get(hass)
    off_id = registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, "aabbcc001122_1_1")
    on_id = registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, "aabbcc001122_1_7")
    assert hass.states.get(off_id).state == STATE_OFF
    assert hass.states.get(on_id).state == STATE_ON


async def test_hidden_outlet_is_config_category(hass, setup_live):
    """The AC/DC Input cuts both DC banks; keep it away from normal controls."""
    registry = er.async_get(hass)
    entry = registry.async_get(
        registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, "aabbcc001122_1_7")
    )
    assert entry.entity_category is EntityCategory.CONFIG


async def test_normal_outlet_has_no_category(hass, setup_live):
    registry = er.async_get(hass)
    entry = registry.async_get(
        registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, "aabbcc001122_1_1")
    )
    assert entry.entity_category is None


async def test_turn_on_calls_power_on_and_refreshes(hass, setup_live, status_1_01):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, "aabbcc001122_1_1")

    with (
        patch(
            "custom_components.surgex.coordinator.SurgexClient.power_on",
            new_callable=AsyncMock,
        ) as power_on,
        patch(
            "custom_components.surgex.coordinator.SurgexClient.current_status",
            return_value=status_1_01,
        ) as status,
    ):
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        await hass.async_block_till_done()

        # The confirming poll is deliberately deferred until the device has
        # settled, so it has not happened yet.
        assert status.await_count == 0

        async_fire_time_changed(
            hass,
            dt_util.utcnow() + timedelta(seconds=REQUEST_REFRESH_COOLDOWN + 1),
        )
        await hass.async_block_till_done()

    power_on.assert_awaited_once_with("1/1")
    # Write-through: state must not wait for the next scheduled poll.
    assert status.await_count >= 1


async def test_turn_on_is_optimistic_while_the_device_reads_back_stale(
    hass, setup_live, status_1_01
):
    """PowerOn succeeds but currentStatus still says off — the switch must read on.

    The device needs a moment to settle; an immediate confirming poll returns
    the pre-command value. Reading back `off` right after a successful turn-on
    is the "reads as broken" failure the design exists to prevent.
    """
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, "aabbcc001122_1_1")
    assert hass.states.get(entity_id).state == STATE_OFF

    with (
        patch(
            "custom_components.surgex.coordinator.SurgexClient.power_on",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.surgex.coordinator.SurgexClient.current_status",
            return_value=status_1_01,  # stale: outlet /1/1 is still off in here
        ),
    ):
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ON


async def test_optimistic_state_yields_to_the_next_poll(hass, setup_live, status_1_01):
    """Optimism is a bridge, not a lie: real data wins once it arrives."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, "aabbcc001122_1_1")

    with (
        patch(
            "custom_components.surgex.coordinator.SurgexClient.power_on",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.surgex.coordinator.SurgexClient.current_status",
            return_value=status_1_01,  # the device never actually came on
        ),
    ):
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == STATE_ON

        async_fire_time_changed(
            hass,
            dt_util.utcnow() + timedelta(seconds=REQUEST_REFRESH_COOLDOWN + 1),
        )
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_OFF


async def test_turn_off_calls_power_off(hass, setup_live, status_1_01):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, "aabbcc001122_1_2")

    with (
        patch(
            "custom_components.surgex.coordinator.SurgexClient.power_off",
            new_callable=AsyncMock,
        ) as power_off,
        patch(
            "custom_components.surgex.coordinator.SurgexClient.current_status",
            return_value=status_1_01,
        ),
    ):
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        await hass.async_block_till_done()

    power_off.assert_awaited_once_with("1/2")


async def test_connection_error_surfaces_as_home_assistant_error(
    hass, setup_live, status_1_01
):
    """A device that drops off Wi-Fi between polls must not raise a raw traceback."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, "aabbcc001122_1_1")

    with (
        patch(
            "custom_components.surgex.coordinator.SurgexClient.power_on",
            new_callable=AsyncMock,
            side_effect=SurgexConnectionError("no route to host"),
        ),
        patch(
            "custom_components.surgex.coordinator.SurgexClient.current_status",
            return_value=status_1_01,
        ),
        pytest.raises(HomeAssistantError) as err,
    ):
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )

    assert not isinstance(err.value, ConfigEntryAuthFailed)
    assert "turn on" in str(err.value)
    assert "/1/1" in str(err.value)


async def test_auth_error_surfaces_as_config_entry_auth_failed(
    hass, setup_live, status_1_01
):
    """A rejected credential must start reauth now, not 30 s from now."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, "aabbcc001122_1_1")

    with (
        patch(
            "custom_components.surgex.coordinator.SurgexClient.power_off",
            new_callable=AsyncMock,
            side_effect=SurgexAuthError("401"),
        ),
        patch(
            "custom_components.surgex.coordinator.SurgexClient.current_status",
            return_value=status_1_01,
        ),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )

    await hass.async_block_till_done()
    flows = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"].get("source") == "reauth"
    ]
    assert flows, "a reauth flow should have been started"


async def test_rebooting_outlet_reports_off_with_raw_state(hass, status_0_5):
    """Outlet /1/4 is state 2 (rebooting) in the documented fixture."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="0eb33ad5a064")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.surgex.coordinator.SurgexClient.current_status",
        return_value=status_0_5,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, "0eb33ad5a064_1_4")
    state = hass.states.get(entity_id)
    assert state.state == STATE_OFF
    assert state.attributes["raw_state"] == 2


async def test_model_generic_outlet_count(hass, status_0_5):
    """A different model yields a different, correct entity set with no code change."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="0eb33ad5a064")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.surgex.coordinator.SurgexClient.current_status",
        return_value=status_0_5,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    switches = [s for s in hass.states.async_all() if s.entity_id.startswith("switch.")]
    assert len(switches) == 6
