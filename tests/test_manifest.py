"""Structural validation of manifest.json and the integration layout.

Containerized `hassfest` (the official validator) requires Docker, which is
not available in this environment. This test covers the same structural
checks hassfest would enforce, so they run on every CI run rather than only
when someone remembers to run hassfest by hand. See .github/workflows/validate.yml
for the real hassfest run via home-assistant/actions/hassfest.
"""

from __future__ import annotations

import json
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
