import dataclasses
from ipaddress import ip_address
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_ZEROCONF
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.surgex.const import CONF_USE_HTTPS, DOMAIN

DISCOVERY = ZeroconfServiceInfo(
    ip_address=ip_address("192.168.1.131"),
    ip_addresses=[ip_address("192.168.1.131")],
    hostname="ametek-AABBCC001122.local.",
    name="Squid Device (AA:BB:CC:00:11:22)._ametekhttp._tcp.local.",
    port=80,
    type="_ametekhttp._tcp.local.",
    properties={
        "serial": "",
        "mac": "AA:BB:CC:00:11:22",
        "ssl": "False",
        "version": "1.01.26815",
        "type": "squid",
    },
)


async def test_zeroconf_prompts_for_credentials(hass, who_are_you, status_1_01):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=DISCOVERY
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    with (
        patch("custom_components.surgex.config_flow.SurgexClient.who_are_you", return_value=who_are_you),
        patch("custom_components.surgex.config_flow.SurgexClient.current_status", return_value=status_1_01),
        patch("custom_components.surgex.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "192.168.1.131"


async def test_zeroconf_aborts_when_type_is_not_squid(hass):
    """A different _ametekhttp._tcp.local. announcer must not be walked into setup."""
    discovery = dataclasses.replace(
        DISCOVERY,
        properties={**DISCOVERY.properties, "type": "not-a-squid"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_a_squid"


async def test_zeroconf_aborts_when_type_is_missing(hass):
    discovery = dataclasses.replace(
        DISCOVERY,
        properties={k: v for k, v in DISCOVERY.properties.items() if k != "type"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_a_squid"


async def test_zeroconf_aborts_when_mac_is_missing(hass):
    discovery = dataclasses.replace(
        DISCOVERY,
        properties={k: v for k, v in DISCOVERY.properties.items() if k != "mac"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_a_squid"


async def test_zeroconf_reads_ssl_property_into_use_https(hass, who_are_you, status_1_01):
    discovery = dataclasses.replace(
        DISCOVERY,
        properties={**DISCOVERY.properties, "ssl": "True"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    with (
        patch("custom_components.surgex.config_flow.SurgexClient.who_are_you", return_value=who_are_you),
        patch("custom_components.surgex.config_flow.SurgexClient.current_status", return_value=status_1_01),
        patch("custom_components.surgex.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_USE_HTTPS] is True


async def test_zeroconf_updates_host_of_existing_entry(hass):
    """A DHCP change must update the entry, not create a duplicate."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.99", CONF_USERNAME: "admin", CONF_PASSWORD: "secret"},
        unique_id="aabbcc001122",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=DISCOVERY
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "192.168.1.131"


async def test_reauth_updates_password(hass, who_are_you, status_1_01):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.131", CONF_USERNAME: "admin", CONF_PASSWORD: "old"},
        unique_id="aabbcc001122",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with (
        patch("custom_components.surgex.config_flow.SurgexClient.who_are_you", return_value=who_are_you),
        patch("custom_components.surgex.config_flow.SurgexClient.current_status", return_value=status_1_01),
        patch("custom_components.surgex.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "new"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new"


async def test_reauth_aborts_when_the_host_is_now_a_different_device(
    hass, who_are_you, status_1_01
):
    """DHCP handed the stored IP to another Squid, or the unit was replaced.

    Reauth must not quietly rebind the entry's entities to different hardware
    while keeping the old MAC as its unique_id.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.131", CONF_USERNAME: "admin", CONF_PASSWORD: "old"},
        unique_id="aabbcc001122",
    )
    entry.add_to_hass(hass)

    other_device = {**who_are_you, "MAC": ["11:22:33:44:55:66"]}

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with (
        patch("custom_components.surgex.config_flow.SurgexClient.who_are_you", return_value=other_device),
        patch("custom_components.surgex.config_flow.SurgexClient.current_status", return_value=status_1_01),
        patch("custom_components.surgex.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "new"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
    assert entry.data[CONF_PASSWORD] == "old"
    assert entry.unique_id == "aabbcc001122"


async def test_options_flow_sets_scan_interval(hass, status_1_01):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.131", CONF_USERNAME: "admin", CONF_PASSWORD: "secret"},
        unique_id="aabbcc001122",
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.surgex.coordinator.SurgexClient.current_status",
        return_value=status_1_01,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 15}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 15
