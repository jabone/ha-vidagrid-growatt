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

**v3.4.0 note (extension v1.3.0):** the browser extension now also forwards
its current bearer token (and an explicit logged-in/out status) to the
integration on every push. Combined with `vidagrid_growatt` v0.5.0+, this
means the integration's own fallback-poll token now refreshes itself
automatically, and Home Assistant will show a persistent notification
telling you to reopen this add-on's Web UI and sign back in if the
browser's session ever logs out -- instead of sensors just quietly going
stale. You still don't need to paste anything into Home Assistant's own
config form if you're running this add-on.

## What it does

- Runs [jlesage/chromium](https://github.com/jlesage/docker-chromium), a
Chromium browser reachable from a web page (no monitor or VNC client
needed), integrated into Home Assistant via **Ingress** (or directly by
IP/port).
- Auto-loads a small custom browser extension that reads whatever auth
token the VidaGrid page currently holds (locally, never sent anywhere
else in raw HTTP-header form) and POSTs fresh battery/diagram/power-curve/
energy-curve data -- plus that token and a login-status flag -- to the
integration's webhook every 3 minutes.
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
- **Inverter serial numbers** — one entry per inverter, exactly as
shown on your VidaGrid portal's device list (e.g.
`SN00000001`, `SN00000002`).
Save.
4. Start the add-on.
5. Open the add-on's web UI — either click **Open Web UI** on its info page
(uses Home Assistant's Ingress) or browse to
`http://<your-pi-address>:5800` directly. You should see a live
Chromium window already navigated to the VidaGrid login page.
6. Sign in normally (solve the captcha yourself — this is the one
unavoidable manual step). You'll need to repeat it again in the future
if the portal ever logs this browser session out -- Home Assistant will
tell you when that happens via a persistent notification, so you don't
need to check manually. Checking any "stay signed in" or "remember me"
option the portal offers on this login screen will make that as
infrequent as possible.
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
- **Login doesn't survive a restart:** as of v3.1.2 this should no longer
happen -- the Chromium profile (`/config/chromium`) is symlinked to
`/data/chromium-profile`, this add-on's own persistent volume, which
survives restarts and ordinary updates (though not a full uninstall).
Check the log for a `Chromium profile persisted at ...` line to confirm.
- **Home Assistant shows "relay needs you to log back in":** open this
add-on's Web UI and sign back into the portal -- as of v3.4.0 this is
reported automatically the moment the extension finds no token in the
page's `localStorage`, rather than you having to notice frozen sensors
first.
- **Sensors stop updating in Home Assistant even though the extension
console shows `pushed ... ok`:** this was tracked down to a Home
Assistant core bug (beta builds around 2026.8), not this add-on --
see [home-assistant/core#178145](https://github.com/home-assistant/core/issues/178145).
It's worked around in the `vidagrid_growatt` integration itself, so a
current install of both should be unaffected either way.

## Resource use

A real Chromium instance running continuously is meaningfully heavier than
a typical add-on. A Raspberry Pi 4/5 with 4GB+ RAM should have headroom
alongside Home Assistant itself, but keep an eye on Settings → System →
Hardware for memory pressure after installing.
