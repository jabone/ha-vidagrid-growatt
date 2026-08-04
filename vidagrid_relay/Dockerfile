# VidaGrid Relay add-on, v3: built on jlesage/chromium instead of
# linuxserver/chromium. The linuxserver image's own entrypoint kept
# requiring more and more container privilege (AppArmor off, SYS_ADMIN,
# then full_access) just to get past early boot, and never actually
# rendered a screen -- that image assumes a normal Docker host, not Home
# Assistant Supervisor's hardened add-on sandbox.
#
# jlesage/chromium is a long-established, actively used base for exactly
# this purpose (see https://github.com/Mincka/ha-addons, a real published
# HA add-on repo doing the same thing), and per its own docs only needs
# the single SYS_ADMIN capability -- no AppArmor or full_access changes --
# for Chromium's own sandbox to work. See config.yaml.
FROM jlesage/chromium:latest

LABEL \
  org.opencontainers.image.title="VidaGrid Relay (Chromium)" \
  org.opencontainers.image.description="Chromium browser add-on that relays VidaGrid/Growatt telemetry to Home Assistant" \
  org.opencontainers.image.source="https://github.com/jabone/ha-vidagrid-growatt" \
  org.opencontainers.image.licenses="MIT"

# jq is used by the cont-init.d script below to read this add-on's
# Configuration tab values (Supervisor writes them to /data/options.json).
RUN apk add --no-cache jq

# Extension TEMPLATE: manifest.json is static, content.js.template still has
# __HA_WEBHOOK_URL__ / __INVERTER_SNS_JSON__ placeholders filled in by the
# cont-init.d script at every container start, into a fresh /tmp location
# (world-readable, so it works no matter which USER_ID the app runs as).
COPY extension /defaults/vidagrid-extension-template

COPY rootfs/etc/cont-init.d/98-vidagrid-config.sh /etc/cont-init.d/98-vidagrid-config.sh
RUN sed -i 's/\r$//' /etc/cont-init.d/98-vidagrid-config.sh \
 && chmod +x /etc/cont-init.d/98-vidagrid-config.sh
