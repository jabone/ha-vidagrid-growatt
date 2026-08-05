# ha-vidagrid-growatt

Home Assistant integration, plus an optional companion add-on, for
Growatt-branded batteries sold behind Base Power's white-label VidaGrid
portal (`growatt-us.vidagrid.com`). This is a second, independent data
source alongside the official Base Power integration -- battery state of
charge, live power flow (solar/grid/load/battery), and today's power and
energy curves, all surfaced as native Home Assistant sensors.

## Why this exists

Base Power's own integration doesn't expose everything the VidaGrid portal
itself tracks per inverter: state of charge, discharge/charge power
breakdown, BDC/BMS details, and separate power-curve/energy-curve history.
This integration talks directly to the (undocumented, unofficial) REST API
behind that portal to fill in the rest.

## How it works

Two independent, cooperating pieces live in this repo:

1. **`custom_components/vidagrid_growatt`** -- the actual Home Assistant
integration (installed via HACS as a custom repository). Exposes
sensors/binary_sensors for each configured inverter, plus one
account-level "relay session" diagnostic sensor.
2. **`vidagrid_relay`** -- an optional Home Assistant add-on that runs a
real Chromium browser, stays logged into the portal, and pushes fresh
telemetry to the integration's webhook every few minutes. **This is the
recommended way to run the integration.** Without it, the integration
can only poll the portal directly using a manually-pasted bearer token
that has been observed expiring in as little as 15-25 minutes.

Two data paths feed the integration:

- **Webhook push (primary, recommended):** the relay add-on's browser
extension reads whatever token the portal page currently holds and POSTs
fresh battery/diagram/power-curve/energy-curve data -- plus its current
token and login status -- to a per-config-entry webhook, roughly every 3
minutes.
- **Fallback poll (best-effort):** the integration also polls the portal
directly on a slower ~20 minute interval, using a bearer token that's
either kept fresh automatically by the relay, or pasted in by hand if
you'd rather not run the relay add-on at all.

## Prerequisites

- **A Growatt/Base Power battery system already commissioned and visible
in the Growatt Shiner portal.** Shiner (`growatt-us.vidagrid.com`, also
reachable as the "Residential Shiner Portal" from growatt.com) is
Growatt's commissioning and monitoring app/portal -- it replaced the
older ShineTools/ShinePhone flow -- and it's what your installer used to
bring the system online. You need a working login for it and at least
one inverter serial number showing data in its device list before this
integration has anything to read.
- **A running Home Assistant instance** with network access to that
Home Assistant instance's webhook endpoint (for the relay push path) and
outbound HTTPS access to `growatt-us.vidagrid.com` (for the fallback
poll).
- **[HACS](https://hacs.xyz/)** installed, to add this repository as a
custom repository and install the integration.
- Optional but recommended: a **Raspberry Pi (or similar always-on
machine) able to run Home Assistant add-ons**, if you plan to run the
VidaGrid Relay add-on described below -- it runs a real Chromium browser
continuously and is meaningfully heavier than a typical add-on.

## Setup

### 1. Install the integration (HACS)

1. In Home Assistant: **HACS -> (menu) -> Custom repositories** -> add
`https://github.com/jabone/ha-vidagrid-growatt` as an **Integration**.
2. Search for "VidaGrid" in HACS and install **VidaGrid (Growatt / Base
Power Batteries)**.
3. Restart Home Assistant.
4. **Settings -> Devices & Services -> Add Integration -> VidaGrid
Growatt.**
5. Fill in the form:
   - **Bearer token** -- leave this **blank** if you're installing the
   relay add-on (recommended, see below). Otherwise paste a token
   copied from your own browser's dev tools -- see "Running without the
   relay add-on" further down.
   - **Base URL** -- defaults to `https://growatt-us.vidagrid.com`,
   correct for most Base Power / Growatt accounts.
   - **Site ID** -- any label you want, used to identify this entry.
   - **Inverter serial numbers** -- comma-separated, exactly as shown in
   your VidaGrid portal's device list.
6. Submit. A persistent notification appears with the webhook URL the
relay add-on needs in the next step.

### 2. Install the relay add-on (recommended)

Full instructions live in [`vidagrid_relay/README.md`](vidagrid_relay/README.md).
Short version: add this same repository as an **add-on** repository,
install **VidaGrid Relay (Chromium)**, paste the webhook URL from step 6
above plus your inverter serial numbers into its Configuration tab, start
it, then open its Web UI once and log into the portal yourself (the
portal's login page requires solving a CAPTCHA, so this one step can't be
automated). After that, the relay keeps itself logged in, keeps pushing
fresh data, and -- as of relay v1.3.0 -- also keeps the integration's
fallback-poll token refreshed automatically. With this path you should
never need to open dev tools or paste a token into Home Assistant.

If the relay's browser session ever does log out (the portal logs it out,
a restart loses the session, etc.), Home Assistant will show a persistent
notification telling you to reopen the add-on's Web UI and sign back in --
the same tradeoff apps like Nest or Apple Home ask you to accept for their
own periodic re-authentication. Check any "stay signed in" option the
portal offers to make that as infrequent as possible.

### Running without the relay add-on

If you'd rather not run a whole Chromium add-on, the integration can run
on the fallback poll alone:

1. Sign into `growatt-us.vidagrid.com` in your own browser.
2. Open dev tools -> Network, reload the page, click any `/web/v1/...`
request.
3. Copy the value after `Bearer ` in that request's `Authorization`
header.
4. Paste it into the integration's Bearer Token field at setup (or later
via **Settings -> Devices & Services -> VidaGrid Growatt ->
Reconfigure**).

This token has been observed expiring in as little as 15-25 minutes, so
expect to repeat this every so often -- sensors hold their last known
value in the meantime rather than going unavailable.

## Entities

Per configured inverter (`sensor.growatt_inverter_<sn>_*`,
`binary_sensor.growatt_inverter_<sn>_*`):

- Battery: level, connect status, BMS type, pack count, bus reference
voltage, discharge/charge power.
- Live diagram: load power, solar power, grid power, battery power, grid
status (on/off-grid).
- Power curve (today, ~5-minute resolution): discharge power, PV power,
and related fields from the portal's "Energy & Power" tab.
- Energy curve (today's totals): consumption, charge, discharge,
from-grid, to-grid.
- Raw diagnostic sensors carrying each endpoint's full unprocessed
payload, for anyone who wants to build their own template sensors.

Account-level (one per config entry, not per inverter):

- **Relay Session Logged Out** (`binary_sensor...._relay_session_logged_out`)
-- diagnostic "problem" sensor, on when the relay's browser session has
logged out. Stays unknown until the relay checks in via webhook at least
once.

## Troubleshooting

- **A sensor is `unavailable`:** most likely the fallback poll's token is
stale and the relay add-on either isn't running or has logged out. Check
the Relay Session Logged Out sensor and the persistent notifications
list.
- **"Relay needs you to log back in" notification:** open **Settings ->
Add-ons -> VidaGrid Relay -> Open Web UI**, sign back into the portal
(check any "stay signed in" option it offers), and things resume
automatically -- nothing else needs to change in Home Assistant.
- **Numbers look frozen:** confirm the relay add-on's log shows `pushed
<serial> ok` messages every few minutes; if it does but Home Assistant
isn't updating, check the integration's logs for `ingest(...)` lines to
confirm the webhook is actually being hit.

## Disclaimer

This integration talks to an undocumented, unofficial API behind the
VidaGrid portal (a Delta Networks (Xiamen) LTD white-label deployment used
by Base Power / Sunrun). It is not affiliated with, endorsed by, or
supported by Base Power, Sunrun, Growatt, or VidaGrid, and the endpoints it
relies on may change or stop working at any time without notice.

## License

MIT -- see [LICENSE](LICENSE).
