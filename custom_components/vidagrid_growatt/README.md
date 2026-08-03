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

## Two data paths (read this first — it explains the setup below)

The portal's login page requires solving a CAPTCHA every time, so this
integration can't log in on its own, and — worse than first assumed — a
copied Bearer token was observed expiring in as little as **~15-25 minutes**,
not the ~30 days the portal's "remember me" option implied. Manually
re-pasting a token every 20 minutes isn't sustainable, so v0.3.0 adds a
second, primary data path:

1. **Webhook push (primary, sustainable):** a small userscript
   (Tampermonkey) runs in your browser tab, which is *already*
   authenticated and stays that way indefinitely — the portal silently
   refreshes its own session in the background without ever needing the
   captcha again. Every few minutes, the script reads whatever token the
   page currently holds (locally, in your browser only) to fetch fresh
   `/battery` and `/diagram` data, then POSTs that **data** — never the
   token — to this integration's webhook. As long as that browser tab
   stays open somewhere, your sensors stay fresh with zero manual steps.
2. **Pasted-token poll (fallback only):** the token you paste at setup is
   used once to validate setup, then polled every 20 minutes as a
   best-effort backup. Expect it to fail routinely once the token expires;
   that's fine — sensors just hold their last good value (from whichever
   path last succeeded) instead of going unavailable.

## Setup

### 1. Initial config (one-time)

1. Open `https://growatt-us.vidagrid.com` in Chrome and sign in normally
   (solve the CAPTCHA yourself — this is the one unavoidable manual step,
   and you should only need to do it again if you explicitly log out).
2. Open Chrome DevTools (F12 or Cmd+Option+I) → **Network** tab. Reload the
   page, then click into your site's device list so a few requests show up.
3. Click any request whose path starts with `/web/v1/` (e.g. `battery`,
   `diagram`). In **Headers**, find `Authorization: Bearer <long string>`
   under Request Headers and copy everything **after** `Bearer `.
4. In Home Assistant, add the **VidaGrid (Growatt / Base Power Batteries)**
   integration and fill in:
   - **Bearer Token**: what you copied (used once to validate, then as a
     fallback poll — see above)
   - **Portal Base URL**: `https://growatt-us.vidagrid.com` (default is fine)
   - **Site ID**: the number in the portal's URL, e.g. `1224587` from
     `.../site_detail/1224587/devices/inverter`. To find it: click **Sites**
     in the portal's left nav, then click into your site.
   - **Inverter Serial Number(s)**: comma-separated, e.g. `SN00000001,SN00000002`

### 2. Get your webhook URL

After setup, ask in Home Assistant (Settings → Devices & Services → this
integration → its device) or check the integration's config entry — the
webhook URL is:

```
http://<your-home-assistant-url>/api/webhook/<webhook_id>
```

`webhook_id` is generated automatically per install and stored with the
config entry (not something you choose). Treat the full URL like a
lightweight secret — anyone with it could push fake data to these sensors.

### 3. Install the relay userscript (makes it self-sustaining)

1. Install the [Tampermonkey](https://www.tampermonkey.net/) browser
   extension (free, Chrome/Firefox/Edge/Safari).
2. Create a new script, paste in `vidagrid_relay.user.js` (packaged
   alongside this integration), and replace the `HA_WEBHOOK_URL` and
   `INVERTER_SNS` placeholders near the top with your real webhook URL and
   serial numbers.
3. Save. Keep a `growatt-us.vidagrid.com` tab open (any tab — it doesn't
   need to be focused, just open and logged in) and it'll relay fresh data
   every 3 minutes automatically, indefinitely, with no further action from
   you.

## What you get

Per inverter: Load Power, Solar Power, Grid Power, Battery Power, Battery
Level (%), a Grid Status on/off sensor, plus battery-pack diagnostics
(Discharge/Charge Power, BMS Type, Pack Count, Connect Status, Bus
Reference Voltage). Two hidden "Raw Data" diagnostic sensors per inverter
expose the full JSON response as attributes — enable them in Settings >
Devices & Services if a value looks wrong.

## Known limitations

- Unofficial, reverse-engineered API — Base Power / Growatt / Delta Networks
  could change or break it without notice.
- The webhook path requires a browser tab to stay open somewhere (any
  device signed into the portal works — doesn't have to be your main
  computer). Without it, you're back to the ~20-minute-token fallback.
- Field mappings in `api.py` are best-effort, built from the portal's
  on-screen labels; check the Raw Data sensors if a value is consistently
  wrong or missing.
