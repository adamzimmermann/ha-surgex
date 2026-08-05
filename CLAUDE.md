# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration (`custom_components/surgex/`) for SurgeX Squid
networked AC/DC PDUs, distributed via HACS. Local polling only, over the device's
own `/api/v1` REST API. Developed against an `SX-DC-8-12-120` on firmware
`1.01.26815`.

## Commands

```bash
.venv/bin/python -m pytest              # full suite (112 tests, ~5s)
.venv/bin/python -m pytest tests/test_api.py::test_who_are_you_returns_payload
.venv/bin/python -m pytest -k config_flow
pip install -r requirements-test.txt    # pytest-homeassistant-custom-component pins the HA version
```

`.venv` is a symlink to `~/.venvs/ha-surgex`. `pytest.ini` sets `asyncio_mode = auto`,
so async tests need no decorator.

Live hardware check (toggles a real outlet and briefly writes a device setting,
restoring both — do not point it at hardware powering anything that matters):

```bash
set -a; . ./.secrets.env; set +a
.venv/bin/python scripts/live_check.py <host-or-ip>
```

CI (`.github/workflows/validate.yml`) runs hassfest, HACS validation, and pytest on
Python 3.14. Hassfest needs Docker and cannot run locally; `tests/test_manifest.py`
mirrors its structural checks so they run every time.

## Architecture

One request per poll cycle feeds every entity. `currentStatus` → parsed into a
frozen `SquidStatus` → all platforms read from that snapshot.

```
api.py        aiohttp client. No HA imports — extractable as a standalone package.
models.py     Pure parsing. No HA and no aiohttp imports.
coordinator.py DataUpdateCoordinator; owns the client and the parse step.
entity.py     SurgexEntity: device identity + the `command()` error-translation helper.
{switch,sensor,binary_sensor,button}.py  Platforms, built from what the device reports.
```

The layering in `api.py` and `models.py` is deliberate and load-bearing — keep HA
imports out of both.

Entities are created from runtime data, not a hardcoded model table: a sensor is
skipped entirely when its value is `None`, a switch exists per reported outlet.
New Squid models generally work without a code change.

### Firmware quirks that shaped the code

Each of these has a comment at the site. Read it before "simplifying" any of them.

- **Malformed 401.** A wrong password gets `Content-Length: 0` followed by a stray
  `0` body. Strict parsers reject the whole response, so the 401 is invisible and a
  bad password looks like a network outage. `api.py::_request` disambiguates by
  probing the unauthenticated `WhoAreYou` endpoint.
- **Deferred confirming poll.** The device does not apply Power commands instantly.
  The coordinator's request-refresh debouncer is `immediate=False` with a
  `REQUEST_REFRESH_COOLDOWN` of 3s; switches hold an optimistic state until that
  poll lands. Making the debouncer immediate reintroduces the stale-readback bug.
- **Temperature.** Reported in Celsius no matter what `temperatureUnits` says (this
  firmware says `"F"`). Verified on hardware by `scripts/live_check.py`.
- **`inputState`** lives on the device object in 1.01 and inside
  `deviceMeasurements` in the 0.5.x docs; `models.py` accepts int, list, and string
  forms.
- **Hidden outlet.** `/1/7` ("AC/DC Input") is a master that feeds every DC bank. It
  is exposed but assigned `EntityCategory.CONFIG`, which keeps it out of area/device
  /floor/label service targets. Do not un-hide it or drop the category.

### Tests

`tests/fake_device.py` is a raw-socket HTTP server, not a mock — it writes response
bytes directly so tests can reproduce the malformed 401 verbatim. Socket-based tests
need the `socket_enabled` fixture. Do not replace it with `aioresponses` (broken
against the aiohttp recent HA ships) or with aiohttp mocking (cannot emit malformed
responses).

Fixtures in `tests/fixtures/` cover both firmware shapes: `current_status_1_01.json`
(captured live) and `current_status_0_5_documented.json` (from AMETEK's docs).
Parsing changes should be checked against both.

## Conventions

- `strings.json` and `translations/en.json` must stay byte-identical —
  `test_manifest.py` enforces it. Edit both.
- Comments explain *why*, especially where the code works around firmware behaviour.
  The existing density is intentional; match it.
- Diagnostics deliberately omit the MAC. Do not add it back.
- `scripts/deploy.sh` is gitignored as a guard: copying this directly into a HA
  config dir would overwrite a HACS-managed install. Installation goes through HACS.
- Bump `version` in `manifest.json` for releases.
