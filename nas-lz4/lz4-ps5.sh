#!/bin/sh
# Runs ps5lz4 inside the ps5-lz4 container as your NAS user.
#   ./lz4-ps5.sh scan --check | start <game> | status | report | stop | ...
DIR="$(cd "$(dirname "$0")" && pwd)"
. "$DIR/.env"
TTY=""
[ -t 0 ] && [ -t 1 ] && TTY="-t"
exec docker exec -i $TTY -u "$PUID:$PGID" "$CONTAINER" ps5lz4 "$@"
