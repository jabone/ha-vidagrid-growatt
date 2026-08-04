# VidaGrid Relay (Chromium) — Home Assistant Add-on

Runs a real Chromium browser as a Home Assistant add-on on the same
Raspberry Pi as Home Assistant itself, so the VidaGrid Growatt integration
gets fresh battery/inverter data every few minutes without you ever having
to paste a new access token again.

**v3.0.0 note:** this add-on was rebuilt on
[jlesage/chromium](https://github.com/jlesage/docker-chromium) after the
original base image (`linuxserver/chromium`) turned out to need
increasingly broad container privileges (AppArmor disabled, then
`SYS_ADMIN`, then `full_access: true`) and still never actually rendered a
screen inside Home Assistant's Supervisor sandbox. `jlesage/chromium` is a
long-established base used by real, working Home Assistant add-ons for
this exact purpose (see
[Mincka/ha-addons](https://github.com/Mincka/ha-addons)) and only needs the
single `SYS_ADMIN` capability.

## What it does

- Runs [jlesage/chromium](https://github.com/jlesage/docker-chromium), a
  Chromium browser reachable from a web page (no monitor or VNC client
  needed), integrated into Home Assistant via **Ingress** (or directly by
  IP/port).
- Auto-loads a small custom browser extension that reads whatever auth
  token the VidaGrid page currently holds (locally, never sent anywhere
  else) and POSTs fresh battery/diagram data to the integration's webhook
  every 3 minutes.
- Auto-opens `growatt-us.vidagrid.com` on start.
- Reads your webhook URL and inverter serial numbers from this add-on's
  own **Configuration** tab in Home Assistant — no editing files, no
  rebuilding. A small startup script bakes those values into the
  extension every time the add-on starts.

## Install

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ (top right) →
   Repositories** → add `https://github.com/jabone/ha-vidagrid-growatt`.
2. Refresh the Add-on Store page, then search "VidaGrid" or scroll to the
   custom-repo section near the bottom. Open **VidaGrid Relay (Chromium)**
   and install it.
3. Open the add-on's **Configuration** tab and fill in:
   - **Webhook URL** — the full webhook URL shown in the VidaGrid Growatt
     integration's persistent notification in Home Assistant (looks like
     `http://<your-ha-address>:8123/api/webhook/<id>`).
   - **Inverter serial numbers** — one entry per inverter (e.g.
     `SN00000001`, `SN00000002`).
   Save.
4. Start the add-on.
5. Open the add-on's web UI — either click **Open Web UI** on its info page
   (uses Home Assistant's Ingress) or browse to
   `http://<your-pi-address>:5800` directly. You should see a live
   Chromium window already navigated to the VidaGrid login page.
6. Sign in normally (solve the captcha yourself — this is the one
   unavoidable manual step, and should only be needed again if this
   session is ever logged out).
7. Leave the add-on running. Open the browser's dev console from within
   that Chromium window (or check the add-on's **Log** tab) to confirm you
   see `[VidaGrid relay] pushed <serial> ok` messages appearing every few
   minutes.
8. Restart the add-on once and re-check that it's still logged in.

## Changing the webhook URL or serial numbers later

Open the add-on's **Configuration** tab, edit the values, save, then
**Restart** the add-on (no rebuild needed) — the startup script re-reads
the Configuration values every time the container starts.

## If something needs fixing

- **Configuration values don't seem to take effect:** check the add-on's
  log tab for a line starting `[vidagrid-relay-init]` — it reports whether
  a webhook URL was found and how many inverters were configured, right
  after each start.
- **Blank/black screen:** wait a few seconds for Chromium to finish
  starting; if it persists, check the add-on's log for errors. Unlike the
  previous (linuxserver-based) version of this add-on, this one should not
  need any additional privilege beyond `SYS_ADMIN`.
- **Login doesn't survive a restart:** this base image persists its full
  profile under `/config` inside the container, which is *not* itself
  guaranteed persistent across Supervisor add-on rebuilds. If logins keep
  getting lost, this is the first thing to revisit (adding a proper
  `/data`-backed persistence step, as done in the Mincka add-on this is
  based on).

## Resource use

A real Chromium instance running continuously is meaningfully heavier than
a typical add-on. A Raspberry Pi 4/5 with 4GB+ RAM should have headroom
alongside Home Assistant itself, but keep an eye on Settings → System →
Hardware for memory pressure after installing.
