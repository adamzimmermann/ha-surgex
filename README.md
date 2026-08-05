# SurgeX for Home Assistant

Local control and monitoring for **SurgeX Squid** networked AC/DC power
distribution units, over the device's own REST API. No cloud, no vendor account.

## Supported hardware

Any Squid speaking the `/api/v1` REST API, including `SX-DC-8-12`,
`SX-DC-8-24`, and `SX-DC-8-1224` in 120 V and 230 V. The integration builds its
entities from what the device reports at runtime, so new models generally work
without a code change.

Older SurgeX PDUs (Axess Elite, Vertical Series+) use a different protocol and
are **not** supported.

Developed against an `SX-DC-8-12-120` on firmware `1.01.26815`.

## What you get

- A switch per outlet and DC bank
- Power, current, voltage, energy, temperature, frequency, and power factor
- Energy is exposed for the Home Assistant **Energy dashboard**
- A reboot button per outlet, using the device's own power-cycle delay
- Surge protection and wiring fault diagnostics

Power and energy are measured at the device input. The hardware has no
per-outlet metering, so these values describe the whole unit, not individual
outlets.

## Installation

**HACS:** add this repository as a custom repository, install **SurgeX**, then
restart Home Assistant.

**Manual:** copy `custom_components/surgex/` into your Home Assistant
`custom_components/` directory and restart.

## Setup

The Squid advertises itself over mDNS, so Home Assistant usually discovers it
and only asks for credentials. Otherwise add it from
**Settings → Devices & services → Add integration → SurgeX** and enter the host.

The default administrator password is `Adm1n-XXXXXX`, where `XXXXXX` is the last
six characters of the device's MAC address, unless it has been changed.

## Options

The polling interval defaults to 30 seconds and is configurable. Switching an
outlet refreshes state immediately rather than waiting for the next poll.

## Licence

MIT
