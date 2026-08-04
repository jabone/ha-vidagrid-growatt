#!/bin/sh
#
# Makes the Chromium profile (the VidaGrid login session, cookies, and
# local storage this add-on depends on) survive not just container
# restarts but full add-on rebuilds and updates.
#
# This base image runs Chromium with --user-data-dir=/config/chromium
# (see jlesage/docker-chromium's rootfs/etc/services.d/app/params).
# /config itself is a Docker VOLUME baked into the base image -- it
# can't be removed or replaced (attempting to do so fails with
# "Resource busy"). /config/chromium is a plain subdirectory of that
# volume, though, so it's safe to swap for a symlink into /data: this
# add-on's own persistent volume, kept across restarts and updates
# (though not a full uninstall).
#
# Runs first (numbered ahead of this base image's own
# 85-take-config-ownership.sh) so that script's ownership/permission
# fixups apply to the real, persistent location once /config/chromium
# becomes a symlink to it.

set -e
set -u

PERSIST_DIR="/data/chromium-profile"
PROFILE_DIR="/config/chromium"

mkdir -p "${PERSIST_DIR}"

if [ -d "${PROFILE_DIR}" ] && [ ! -L "${PROFILE_DIR}" ]; then
cp -a "${PROFILE_DIR}/." "${PERSIST_DIR}/" 2>/dev/null || true
rm -rf "${PROFILE_DIR}"
ln -s "${PERSIST_DIR}" "${PROFILE_DIR}"
elif [ ! -e "${PROFILE_DIR}" ]; then
ln -s "${PERSIST_DIR}" "${PROFILE_DIR}"
fi

# The base image's own ownership-fixup script (85-take-config-ownership.sh)
# walks /config with a recursive chown, but that does not follow a symlink
# it encounters *during* traversal (only the initial argument is
# dereferenced) -- so it would chown the /config/chromium symlink itself
# and never touch the real directory under /data. Do that explicitly here,
# or Chromium (which runs as USER_ID:GROUP_ID, not root) can't write to
# its own profile and crash-loops (exit 21) instead of rendering anything.
chown -R "${USER_ID:-1000}:${GROUP_ID:-1000}" "${PERSIST_DIR}"

echo "[vidagrid-relay-init] Chromium profile persisted at ${PERSIST_DIR} (symlinked from ${PROFILE_DIR})"

# vim:ft=sh:ts=4:sw=4:et:sts=4
