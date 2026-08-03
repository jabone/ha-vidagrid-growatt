# VidaGrid Relay (Chromium) — Home Assistant Add-on

Runs a real Chromium browser as a Home Assistant add-on on the same
Raspberry Pi as Home Assistant itself, so the VidaGrid Growatt integration
gets fresh battery/inverter data every few minutes without you ever having
to paste a new access token again.

**Read this first:** this add-on hasn't been test-run on real Raspberry Pi
hardware or a live Supervisor install as part of building it (no Pi was
available to verify against) — the pieces are built from the base image's
documented behavior and standard Home Assistant/s6-overlay add-on
conventions, but treat the first install as a "let's see if this needs a
small tweak" step rather than a guaranteed one-shot success. The most likely
things to need adjusting are the `jq`/package-manager detection in the
Dockerfile if the base image changes its underlying OS, or the `CHROME_CLI`
flag if the base image's flag-passing behavior differs from its docs.

## What it does

- Runs [linuxserver/chromium](https://docs.linuxserver.io/images/docker-chromium/),
  a full Chromium desktop reachable from any browser via a built-in web
  screen (KasmVNC) on port 3000 — no monitor or VNC client needed.
- Auto-loads a small custom browser extension (`extension/`) that reads
  whatever auth token the VidaGrid page currently holds (locally, never
  sent anywhere else) and POSTs fresh battery/diagram data to the
  integration's webhook every 3 minutes.
- Auto-opens `growatt-us.vidagrid.com` on start.
- Reads your webhook URL and inverter serial numbers from this add-on's own
  **Configuration** tab in Home Assistant — no forking the repo, no editing
  files, no rebuilding. A small startup script bakes those values into the
  extension every time the add-on starts.

## Install

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ (top right) →
   Repositories** → add `https://github.com/jabone/ha-vidagrid-growatt`.
2. Refresh the Add-on Store page (new repos don't always show up until you
   reload), then search "VidaGrid" or scroll to the custom-repo section near
   the bottom. Open **VidaGrid Relay (Chromium)** and install it.
3. Open the add-on's **Configuration** tab and fill in:
   - **Webhook URL** — the full webhook URL shown in the VidaGrid Growatt
     integration's persistent notification in Home Assistant (looks like
     `http://<your-ha-address>:8123/api/webhook/<id>`).
   - **Inverter serial numbers** — one entry per inverter (e.g.
     `SN00000001`, `SN00000002`).
   Save.
4. Start the add-on.
5. Open `http://<your-pi-address>:3000` in any browser on your network —
   you'll see a live Chromium desktop already navigated to the VidaGrid
   login page.
6. Sign in normally (solve the captcha yourself — this is the one
   unavoidable manual step, and should only be needed again if this session
   is ever logged out).
7. Leave the add-on running. Open the browser console (F12 in that
   web-Chromium window) to confirm you see `[VidaGrid relay] pushed
   <serial> ok` messages appearing every few minutes.
8. Restart the add-on once and re-check that it's still logged in — if it
   isn't, the browser profile isn't persisting across restarts and the
   volume mapping needs adjusting (see note below).

## Changing the webhook URL or serial numbers later

Open the add-on's **Configuration** tab, edit the values, save, then
**Restart** the add-on (no rebuild needed) — a startup script re-reads the
Configuration values every time the container starts.

## If something needs fixing

- **Configuration values don't seem to take effect:** check the add-on's
  log tab for a line starting `[vidagrid-relay-init]` — it reports whether
  a webhook URL was found and how many inverters were configured, right
  after each start.
- **Extension doesn't seem to load:** check the base image's current docs
  for `CHROME_CLI` syntax (it's passed as one literal string of CLI flags)
  — it may need quoting adjustments depending on the installed image version.
- **Login doesn't survive a restart:** the base image persists its browser
  profile at `/config` inside the container. This add-on doesn't currently
  map that to a named persistent volume (kept simple to avoid an untested
  path-remapping step) — Supervisor generally keeps add-on containers
  intact across normal Home Assistant restarts, but a full add-on
  rebuild/reinstall will lose the session and require logging in again.

## Resource use

A real Chromium instance running continuously is meaningfully heavier than
a typical add-on. A Raspberry Pi 4/5 with 4GB+ RAM should have headroom
alongside Home Assistant itself, but keep an eye on Settings → System →
Hardware for memory pressure after installing.
