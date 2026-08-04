#!/bin/sh
#
# Makes the Chromium profile (the VidaGrid login session, cookies, and
# local storage this add-on depends on) survive not just container
# restarts but full add-on rebuilds and updates.
#
# This base image stores its profile at /config inside the container.
# That path is only as persistent as the container's own writable layer
# -- fine across a plain restart, but wiped whenever Supervisor rebuilds
# the image (e.g. after a config.yaml/version bump). /data, on the other
# hand, is this add-on's dedicated persistent volume, kept across
# restarts and updates (though not a full uninstall).
#
# This script runs first (numbered ahead of this base image's own
# 85-take-config-ownership.sh) so that script's ownership/permission
# fixups apply to the real, persistent location once /config becomes a
# symlink to it.

set -e
set -u

PERSIST_DIR="/data/chromium-profile"
CONFIG_DIR="/config"

mkdir -p "${PERSIST_DIR}"

if [ -d "${CONFIG_DIR}" ] && [ ! -L "${CONFIG_DIR}" ]; then
    # First run against this persistent volume: seed it with whatever
        # the image shipped at /config, then replace /config with a symlink.
            cp -a "${CONFIG_DIR}/." "${PERSIST_DIR}/" 2>/dev/null || true
                rm -rf "${CONFIG_DIR}"
                    ln -s "${PERSIST_DIR}" "${CONFIG_DIR}"
                    elif [ ! -e "${CONFIG_DIR}" ]; then
                        ln -s "${PERSIST_DIR}" "${CONFIG_DIR}"
                        fi

                        echo "[vidagrid-relay-init] Chromium profile persisted at ${PERSIST_DIR} (symlinked from ${CONFIG_DIR})"

                        # vim:ft=sh:ts=4:sw=4:et:sts=4
                        
