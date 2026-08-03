# VidaGrid Growatt (Base Power Batteries) — Custom Integration

Reads live battery/inverter data directly from the VidaGrid portal
(`growatt-us.vidagrid.com`) that Base Power's Growatt-branded batteries
report to. This is the same backend behind the "Shiner" consumer app, and
in testing it returned real, current data even when the portal's own
Devices list showed the inverters as "Offline" — a cosmetic bug in that
list view, not a sign of anything actually being down.

This is independent of, and does not replace, the official `jerrit/ha-base-power`
HACS integration. It's a second, corroborating data source built after
`jerrit/ha-base-power` v1.9.0 was found to have several real bugs (billing
parser, unsafe grid-outage default, etc.) — see the upstream PR #5 / Issue #6
filed against that integration for details.

## Why you have to paste in a token

The portal's own login page requires solving a CAPTCHA every time. That
means this integration cannot log in for you — Home Assistant integrations
are not allowed to (and this one deliberately does not attempt to) bypass
CAPTCHAs. Instead, you sign in through your normal browser and hand this
integration the Bearer token your browser already holds.

Based on the portal's "Remember me for 30 days" option, that token is
likely valid for about a month. When it expires, Home Assistant's normal
re-authentication flow will pop up a notification asking you to paste a
new one — no reinstall needed.

## Getting your Bearer token

1. Open `https://growatt-us.vidagrid.com` in Chrome and sign in normally
   (solve the CAPTCHA yourself — this is the one manual step).
2. Open Chrome DevTools (F12 or Cmd+Option+I) and switch to the **Network** tab.
3. Reload the page, then click into your site's device list so a few requests
   show up.
4. Click any request whose path starts with `/web/v1/` (e.g. `battery`,
   `diagram`, `production`).
5. In the **Headers** panel, find `Authorization: Bearer <long string>` under
   Request Headers. Copy everything **after** `Bearer ` (not the word
   "Bearer" itself).
6. In Home Assistant, add the **VidaGrid (Growatt / Base Power Batteries)**
   integration and paste that value into the "Bearer Token" field, along
   with:
   - **Portal Base URL**: `https://growatt-us.vidagrid.com` (default is fine)
   - **Site ID**: the number in the portal's URL, e.g. `1224587` from
     `.../site_detail/1224587/devices/inverter`
   - **Inverter Serial Number(s)**: comma-separated, e.g. `SN00000001,SN00000002`

## What you get

Per inverter: Load Power, Solar Power, Grid Power, Battery Power, Battery
Level (%), a Grid Status on/off sensor, plus battery-pack diagnostics
(Discharge/Charge Power, BMS Type, Pack Count, Connect Status, Bus
Reference Voltage). Two hidden "Raw Data" diagnostic sensors per inverter
expose the full JSON response as attributes — enable them in Settings >
Devices & Services if a value looks wrong, since the exact field-name
mapping in `api.py` was built from the portal's on-screen labels rather
than a captured response body (the CAPTCHA-gated login blocked a full API
capture) and may need small corrections once real data flows through it.

## Known limitations

- Unofficial, reverse-engineered API — Base Power / Growatt / Delta Networks
  could change or break it without notice.
- Manual token refresh roughly monthly.
- Field mappings in `api.py` are best-effort; check the Raw Data sensors if
  a value is consistently wrong or missing, and adjust the key names in
  `_dig()` calls to match what you see there.
