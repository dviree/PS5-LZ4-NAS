#!/bin/sh
# Runs ps5lz4 inside the ps5-lz4 container as your NAS user.
#   ./lz4-ps5.sh scan --check | start <game> | status | report | stop | ...
# stdin is not attached (no -i/-t): ps5lz4 never reads input, and an
# attached stdin would swallow the lines pasted after this command.
DIR="$(cd "$(dirname "$0")" && pwd)"
. "$DIR/.env"
exec docker exec -u "$PUID:$PGID" "$CONTAINER" ps5lz4 "$@"
