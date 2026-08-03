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

COPY extension /defaults/vidagrid-extension

# CHROME_CLI is read directly by the base image's own launcher; baking it in
# here (rather than passing at `docker run` time) keeps the extension wired
# up automatically for the Home Assistant add-on config below.
ENV CHROME_CLI="--load-extension=/defaults/vidagrid-extension https://growatt-us.vidagrid.com/main/overview"
