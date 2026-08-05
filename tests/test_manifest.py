"""Structural validation of manifest.json and the integration layout.

Containerized `hassfest` (the official validator) requires Docker, which is
not available in this environment. This test covers the same structural
checks hassfest would enforce, so they run on every CI run rather than only
when someone remembers to run hassfest by hand. See .github/workflows/validate.yml
for the real hassfest run via home-assistant/actions/hassfest.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from custom_components.surgex import const

INTEGRATION_DIR = Path(__file__).parent.parent / "custom_components" / "surgex"


def test_manifest_json_is_valid_json():
    manifest = json.loads((INTEGRATION_DIR / "manifest.json").read_text())
    assert manifest["domain"] == "surgex"


def test_every_platform_module_exists():
    for platform in const.PLATFORMS:
        assert (INTEGRATION_DIR / f"{platform.value}.py").is_file(), (
            f"const.PLATFORMS lists {platform.value!r} but "
            f"{platform.value}.py is missing from {INTEGRATION_DIR}"
        )


async def test_integration_loads_via_ha_loader(hass: HomeAssistant):
    """Exercise the same manifest loading path hassfest and HA core use."""
    integration = await async_get_integration(hass, "surgex")

    assert integration.domain == "surgex"
    manifest = integration.manifest

    assert manifest["domain"] == "surgex"
    assert manifest["config_flow"] is True
    assert isinstance(manifest["version"], str) and manifest["version"]
    assert manifest["iot_class"] == "local_polling"

    documentation = manifest["documentation"]
    assert documentation.startswith("https://")
    issue_tracker = manifest["issue_tracker"]
    assert issue_tracker.startswith("https://")

    codeowners = manifest["codeowners"]
    assert isinstance(codeowners, list) and codeowners

    assert manifest["requirements"] == []
    assert manifest["zeroconf"] == ["_ametekhttp._tcp.local."]


def test_english_translations_match_strings_json():
    """translations/en.json is the English rendering of strings.json.

    They are maintained by hand, so nothing but a test stops one from gaining
    a key the other lacks -- which shows up as a raw key like
    `unique_id_mismatch` in the UI rather than a sentence.
    """
    strings = (INTEGRATION_DIR / "strings.json").read_bytes()
    english = (INTEGRATION_DIR / "translations" / "en.json").read_bytes()
    assert strings == english, (
        "strings.json and translations/en.json have drifted apart; "
        "they must stay byte-identical"
    )


def test_every_config_flow_abort_and_error_reason_has_a_string():
    """Any reason the flow can emit must resolve to a sentence, not a raw key."""
    source = (INTEGRATION_DIR / "config_flow.py").read_text()
    config = json.loads((INTEGRATION_DIR / "strings.json").read_text())["config"]

    aborts = re.findall(r'async_abort\(reason="([a-z_]+)"\)', source)
    aborts += re.findall(r'_abort_if_unique_id_mismatch\(reason="([a-z_]+)"\)', source)
    for reason in aborts:
        assert reason in config["abort"], f"abort reason {reason!r} has no string"

    for error in re.findall(r'errors\["base"\] = "([a-z_]+)"', source):
        assert error in config["error"], f"error key {error!r} has no string"
