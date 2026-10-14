#!/bin/sh
# Container start (NAS boot, Watchtower update, manual restart): continue an
# unfinished queue as the NAS user, then idle until `docker exec` jobs arrive.
if [ -n "${PUID:-}" ] && [ -n "${PGID:-}" ] && [ "$(id -u)" = 0 ]; then
  setpriv --reuid="$PUID" --regid="$PGID" --clear-groups \
    ps5lz4 start --resume 2>&1 | grep -v '^no unfinished queue' || true
fi
exec sleep infinity
