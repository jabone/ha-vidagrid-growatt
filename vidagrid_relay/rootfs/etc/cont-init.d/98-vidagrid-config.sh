#!/bin/sh
#
# Turns this add-on's Home Assistant "Configuration" tab values into the
# actual browser extension Chromium loads. Runs once at every container
# start (s6-overlay convention, same as this base image's own init
# scripts), as root, before the app drops to its unprivileged user -- so
# saving new options + restarting the add-on is enough, no rebuild needed.
#
# Supervisor writes whatever the user entered in the Configuration tab to
# /data/options.json. We read webhook_url and inverter_sns out of it and
# substitute them into the content.js template, writing the real file to
# a fresh /tmp location (world-readable, so it works no matter which
# USER_ID Chromium itself ends up running as).

set -e
set -u

TEMPLATE_DIR="/defaults/vidagrid-extension-template"
RUNTIME_DIR="/tmp/vidagrid-extension"
OPTIONS_FILE="/data/options.json"

mkdir -p "${RUNTIME_DIR}"
cp "${TEMPLATE_DIR}/browser-manifest.src.json" "${RUNTIME_DIR}/manifest.json"

if [ -f "${OPTIONS_FILE}" ]; then
    WEBHOOK_URL=$(jq -r '.webhook_url // empty' "${OPTIONS_FILE}")
    SNS_JSON=$(jq -c '.inverter_sns // []' "${OPTIONS_FILE}")
else
    WEBHOOK_URL=""
    SNS_JSON="[]"
fi

sed \
    -e "s#__HA_WEBHOOK_URL__#${WEBHOOK_URL}#" \
    -e "s#__INVERTER_SNS_JSON__#${SNS_JSON}#" \
    "${TEMPLATE_DIR}/content.js.template" > "${RUNTIME_DIR}/content.js"

# Chromium runs as USER_ID/GROUP_ID (default 1000), not root -- make sure
# it can read the extension we just wrote as root.
chmod -R a+rX "${RUNTIME_DIR}"

SN_COUNT=$(echo "${SNS_JSON}" | jq 'length')
if [ -n "${WEBHOOK_URL}" ]; then
    echo "[vidagrid-relay-init] configured: webhook set, ${SN_COUNT} inverter(s)"
else
    echo "[vidagrid-relay-init] WARNING: webhook_url is empty -- set it in this add-on's Configuration tab, then restart"
fi

# vim:ft=sh:ts=4:sw=4:et:sts=4
