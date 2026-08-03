# VidaGrid Relay add-on: a full Chromium browser (with a web-based screen,
# no monitor needed) that stays logged into the VidaGrid/Growatt portal and
# relays battery/inverter telemetry to the vidagrid_growatt integration's
# webhook. Built on linuxserver.io's Chromium image, which already ships a
# KasmVNC web UI (ports 3000/3001) and supports aarch64 (Raspberry Pi 4/5)
# and amd64.
#
# The only thing added on top is our own unpacked Chrome extension
# (extension/) loaded via the base image's CHROME_CLI mechanism, plus the
# target URL to auto-open on start.
FROM lscr.io/linuxserver/chromium:latest

# jq is used by the cont-init.d script below to read this add-on's
# Home Assistant "Configuration" tab values (Supervisor writes them to
# /data/options.json). Installed with whichever package manager the base
# image actually has, since that can vary by release.
RUN if command -v apt-get >/dev/null 2>&1; then \
      apt-get update && apt-get install -y --no-install-recommends jq && rm -rf /var/lib/apt/lists/*; \
    elif command -v apk >/dev/null 2>&1; then \
      apk add --no-cache jq; \
    fi

# This is a TEMPLATE copy of the extension -- manifest.json is static, but
# content.js.template still has __HA_WEBHOOK_URL__ / __INVERTER_SNS_JSON__
# placeholders. The cont-init.d script below fills those in from Supervisor
# options at every container start and writes the real, loadable extension
# to /config/vidagrid-extension.
COPY extension /defaults/vidagrid-extension-template

# s6-overlay (used by all linuxserver.io images) runs every executable
# script under /etc/cont-init.d/ once at container start, before services
# start. This is what turns the Configuration tab's saved values into the
# actual extension Chromium loads -- so changing options + restarting the
# add-on is enough; no image rebuild needed.
COPY rootfs/etc/cont-init.d/99-vidagrid-config /etc/cont-init.d/99-vidagrid-config
RUN chmod +x /etc/cont-init.d/99-vidagrid-config

# Chromium loads the extension from the runtime location the init script
# writes to (under /config, which this base image already persists across
# restarts), not the read-only template copied in above.
ENV CHROME_CLI="--load-extension=/config/vidagrid-extension https://growatt-us.vidagrid.com/main/overview"
