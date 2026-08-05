from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.surgex.api import SurgexAuthError, SurgexConnectionError
from custom_components.surgex.const import DOMAIN

USER_INPUT = {
    CONF_HOST: "192.168.1.131",
    CONF_PORT: 80,
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "secret",
}


async def test_user_flow_creates_entry(hass, who_are_you, status_1_01):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    with (
        patch("custom_components.surgex.config_flow.SurgexClient.who_are_you", return_value=who_are_you),
        patch("custom_components.surgex.config_flow.SurgexClient.current_status", return_value=status_1_01),
        patch("custom_components.surgex.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SX-DC-8-12-120"
    assert result["result"].unique_id == "aabbcc001122"


async def test_unreachable_host_shows_cannot_connect(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with patch(
        "custom_components.surgex.config_flow.SurgexClient.who_are_you",
        side_effect=SurgexConnectionError("no route"),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_bad_credentials_shows_invalid_auth(hass, who_are_you):
    """WhoAreYou succeeds, currentStatus 401s — this must not read as 'cannot connect'."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with (
        patch("custom_components.surgex.config_flow.SurgexClient.who_are_you", return_value=who_are_you),
        patch("custom_components.surgex.config_flow.SurgexClient.current_status", side_effect=SurgexAuthError("401")),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_duplicate_device_aborts(hass, who_are_you, status_1_01):
    MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id="aabbcc001122").add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with (
        patch("custom_components.surgex.config_flow.SurgexClient.who_are_you", return_value=who_are_you),
        patch("custom_components.surgex.config_flow.SurgexClient.current_status", return_value=status_1_01),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_non_squid_device_shows_not_a_squid_error(hass):
    """A WhoAreYou body without a MAC is not a Squid."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with patch(
        "custom_components.surgex.config_flow.SurgexClient.who_are_you",
        return_value={"model": "Some Printer"},
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "not_a_squid"}
