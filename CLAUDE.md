# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration (`custom_components/surgex/`) for SurgeX Squid
networked AC/DC PDUs, distributed via HACS. Local polling only, over the device's
own `/api/v1` REST API. Developed against an `SX-DC-8-12-120` on firmware
`1.01.26815`.

## Commands

```bash
.venv/bin/python -m pytest              # full suite (121 tests, ~5s)
.venv/bin/python -m pytest tests/test_api.py::test_who_are_you_returns_payload
.venv/bin/python -m pytest -k config_flow
pip install -r requirements-test.txt    # pytest-homeassistant-custom-component pins the HA version
```

`.venv` is a symlink to `~/.venvs/ha-surgex`. `pytest.ini` sets `asyncio_mode = auto`,
so async tests need no decorator.

Live hardware check. It powers one outlet off and back on, restoring what it
found; it writes no device settings, and the energy-reset check skips itself
unless the counter already reads 0. **Confirm with the device owner before
running it** — only they know whether the PDU is powering something that
matters right now.

```bash
set -a; . ./.secrets.env; set +a          # SURGEX_USER, SURGEX_PASS, SURGEX_HOST
.venv/bin/python scripts/live_check.py [host-or-ip]
```

Keep that script to checks that stay useful. One-off investigations that have
been answered belong in a comment, not in code that re-runs forever — the two
that used to live there both wrote to the device, and one of them wedged it
(see the hardware note below).

CI (`.github/workflows/validate.yml`) runs hassfest, HACS validation, and pytest on
Python 3.14, on pushes to `main`, pull requests, and `v*` tags. Hassfest needs
Docker and cannot run locally; `tests/test_manifest.py` mirrors its structural
checks so they run every time.

**Pytest runs as a matrix over two Home Assistant versions**: current
(`requirements-test.txt`) and the oldest supported (`requirements-test-min.txt`,
pinned to the `homeassistant` floor in `hacs.json`). A CI step fails if those two
drift apart, because a floor nobody tests is not a floor.

To reproduce the minimum-version run locally:

```bash
python3.14 -m venv /tmp/venv-min
/tmp/venv-min/bin/pip install -r requirements-test-min.txt
/tmp/venv-min/bin/python -m pytest -q
```

The dependency HA pins matters as much as HA's own API surface. `encode_basic_auth`
shipped in aiohttp 3.14, and HA carried aiohttp 3.13 until 2026.7 — so code using it
was fine on current HA and broken on everything from 2026.2 to 2026.6. When reaching
for a library API, check the version HA pins at the floor, not the one in `.venv`.

## Releasing

**The git tag must be `v` + the `version` in `manifest.json`, exactly.** Bump the
manifest and commit it *before* tagging. HACS and Home Assistant's device registry
both read that field, so a tag that disagrees ships an integration misreporting
its own version — which is what happened to `v0.1.1` (tagged while the manifest
still said `0.1.0`).

The `Manifest version matches tag` CI job fails the run when they disagree, but
it is detective, not preventive: it runs after the tag exists, because nothing
earlier knows the tag name. Recovery is to bump the manifest, delete both the tag
and the release, and tag again.

`test_manifest.py` cannot catch this — it only asserts the version is a non-empty
string, which a stale value satisfies perfectly.

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
  firmware says `"F"`). Confirmed twice on hardware by flipping the setting and
  watching the payload not move. That check has been removed — it was the only code
  that wrote a device setting, and its `finally`-block restore assumed the restore
  could not itself fail. Do not reintroduce it to re-answer a settled question.
- **The HTTP server is fragile.** It is small and single-threaded, and a request
  that hangs rather than failing ties up a connection slot. Two runs of a probe
  that hung (the unscoped `/ResetEnergyUsage`) exhausted the pool and the device
  answered `503 Server Busy` to *everything*, including Home Assistant's polling,
  for eight minutes before recovering on its own. Treat back-to-back scripted
  requests against real hardware with care, and never add a probe whose failure
  mode is a hang.
- **`ResetEnergyUsage` is device-scoped** (`{device_path}/ResetEnergyUsage`). The
  unscoped path does not fail cleanly — it hangs, per the note above.
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

`test_live_check.py` loads `scripts/live_check.py` by path and covers its two
consequential guards: the one that refuses to reset an energy counter with data on
it, and the one asserting a bad password stays distinguishable from an unreachable
device. Both are cases where a silently broken check is worse than no check —
verify changes to them by mutation (break the guard, confirm exactly one test
fails), not by watching them pass.

## Conventions

- `strings.json` and `translations/en.json` must stay byte-identical —
  `test_manifest.py` enforces it. Edit both.
- Comments explain *why*, especially where the code works around firmware behaviour.
  The existing density is intentional; match it.
- Diagnostics deliberately omit the MAC. Do not add it back.
- `scripts/deploy.sh` is gitignored as a guard: copying this directly into a HA
  config dir would overwrite a HACS-managed install. Installation goes through HACS.
- See **Releasing** above before tagging: the manifest version and the tag must
  match, and the manifest bump comes first.
