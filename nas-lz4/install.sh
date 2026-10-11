#!/bin/bash
# Installs ps5-lz4 (LZ4 HC packing of PS5 games for APR-EMU) on the NAS.
#
#   sudo -i
#   bash /volume2/docker/ps5-lz4/src/nas-lz4/install.sh --check   # look only
#   nohup bash /volume2/docker/ps5-lz4/src/nas-lz4/install.sh > /volume2/docker/ps5-lz4/install.log 2>&1 &
#
# Paths and user can be changed with environment variables (defaults below).
# Nothing outside BASE and OUTPUT is changed, no other container is touched,
# and the game library is only ever mounted read-only.
set -euo pipefail

LIBRARY="${LIBRARY:-/volume1/games/roms/ps5}"
OUTPUT="${OUTPUT:-/volume1/games/ps5-lz4}"
BASE="${BASE:-/volume2/docker/ps5-lz4}"
NAS_USER="${NAS_USER:-sureahad}"
IMAGE="${IMAGE:-ps5-lz4:local}"
CONTAINER="${CONTAINER:-ps5-lz4}"
LEVEL="${LEVEL:-9}"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

say()  { printf '%s %s\n' "[$(date '+%H:%M:%S')]" "$*"; }
ok()   { printf '  [ok]   %s\n' "$*"; }
warn() { printf '  [warn] %s\n' "$*"; }
die()  { printf '  [FAIL] %s\n' "$*"; exit 1; }

# ---------------------------------------------------------------- preflight
say "Preflight (nothing is changed in this step)"
[ "$(id -u)" = 0 ] || die "run as root (sudo -i)"
[ -f "$REPO/nas-lz4/Dockerfile" ] && [ -f "$REPO/tests/host/Makefile" ] || die "run this from the repository checkout ($REPO)"

arch="$(uname -m)"
case "$arch" in
  x86_64|aarch64) ok "architecture $arch" ;;
  *) die "architecture $arch is not supported (x86_64 or aarch64)" ;;
esac
ok "cpus $(nproc), kernel $(uname -r)"

command -v docker >/dev/null || die "docker not found"
docker info >/dev/null 2>&1 || die "docker daemon not reachable"
ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?')"
COMPOSE=""
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
fi
if [ -n "$COMPOSE" ]; then ok "compose: $($COMPOSE version 2>/dev/null | head -1)"; else warn "no docker compose; plain docker run will be used"; fi

id "$NAS_USER" >/dev/null 2>&1 || die "user $NAS_USER not found (set NAS_USER=...)"
PUID="$(id -u "$NAS_USER")"; PGID="$(id -g "$NAS_USER")"
ok "files will be owned by $NAS_USER ($PUID:$PGID)"

[ -d "$LIBRARY" ] || die "library $LIBRARY does not exist"
n_exfat=$(find "$LIBRARY/" -maxdepth 4 -iname '*.exfat' -type f 2>/dev/null | wc -l)
n_pfsc=$(find "$LIBRARY/" -maxdepth 4 -iname '*.ffpfsc' -type f 2>/dev/null | wc -l)
n_pfs=$(find "$LIBRARY/" -maxdepth 4 -iname '*.ffpfs' -type f 2>/dev/null | wc -l)
n_vhash=$(find "$LIBRARY/" -maxdepth 4 -iname '*.ffpfsc.vhash' -type f 2>/dev/null | wc -l)
n_dirs=$(find "$LIBRARY/" -maxdepth 4 -name eboot.bin -type f 2>/dev/null | wc -l)
ok "library $LIBRARY: $n_exfat .exfat, $n_pfsc .ffpfsc ($n_vhash with .vhash), $n_pfs .ffpfs, $n_dirs game folders"

for v in "$(dirname "$OUTPUT")" "$(dirname "$BASE")"; do
  [ -d "$v" ] || die "$v does not exist"
done
df -h "$(dirname "$OUTPUT")" "$(dirname "$BASE")" | sed 's/^/         /'
if [ "$(df -P "$OUTPUT" 2>/dev/null | awk 'NR==2{print $1}')" = "$(df -P "$BASE" 2>/dev/null | awk 'NR==2{print $1}')" ] && [ -d "$OUTPUT" ] && [ -d "$BASE" ]; then
  warn "OUTPUT and BASE are on the same volume; large temporary data goes to OUTPUT"
fi

if [ -d "$OUTPUT" ]; then
  ok "output $OUTPUT exists ($(find "$OUTPUT" -mindepth 1 -maxdepth 1 | wc -l) entries)"
  if [ -d "$OUTPUT/.work" ] && [ -n "$(ls -A "$OUTPUT/.work" 2>/dev/null)" ]; then
    warn "$OUTPUT/.work already has content (from an earlier script?): $(ls -A "$OUTPUT/.work" | head -5 | tr '\n' ' ')"
    warn "it is left alone; ps5-lz4 uses its own $OUTPUT/.ps5lz4-work"
  fi
else
  ok "output $OUTPUT will be created"
fi

if [ -d "$BASE" ]; then
  ok "base $BASE exists: $(ls -A "$BASE" | tr '\n' ' ')"
else
  ok "base $BASE will be created"
fi

existing="$(docker ps -a --filter "name=^/${CONTAINER}$" --format '{{.Image}} {{.Status}}' || true)"
if [ -n "$existing" ]; then
  project="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' "$CONTAINER" 2>/dev/null || true)"
  img="${existing%% *}"
  if [ "$img" = "$IMAGE" ] || [ "$project" = "ps5-lz4" ]; then
    ok "container $CONTAINER exists ($existing); it will be recreated"
  else
    die "a different container is already named $CONTAINER ($existing); set CONTAINER=... to use another name"
  fi
else
  ok "no container named $CONTAINER yet"
fi
ok "other containers: $(docker ps --format '{{.Names}}' | grep -vx "$CONTAINER" | tr '\n' ' ') (not touched)"

if [ "$CHECK_ONLY" = 1 ]; then
  say "Check finished. Nothing was changed. Run without --check to install."
  exit 0
fi

# ---------------------------------------------------------------- install
say "Installing into $BASE"
mkdir -p "$BASE/state" "$BASE/logs" "$BASE/reports" "$OUTPUT"
chown "$PUID:$PGID" "$BASE/state" "$BASE/logs" "$BASE/reports" "$OUTPUT"
install -d -o "$PUID" -g "$PGID" "$OUTPUT/.ps5lz4-work"

backup="$BASE/backup-$(date +%Y%m%d-%H%M%S)"
for f in docker-compose.yml .env lz4-ps5.sh Dockerfile; do
  if [ -e "$BASE/$f" ]; then
    mkdir -p "$backup"
    cp -a "$BASE/$f" "$backup/"
    say "backed up existing $f to $backup/"
  fi
done
if [ -e "$BASE/Dockerfile" ]; then
  mv "$BASE/Dockerfile" "$BASE/Dockerfile.old-script"
  say "the earlier script's Dockerfile was renamed to Dockerfile.old-script (not used)"
fi

TZ_NAME="$(cat /etc/timezone 2>/dev/null || readlink /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||' || echo UTC)"
cat > "$BASE/.env" <<EOF
PUID=$PUID
PGID=$PGID
LIBRARY=$LIBRARY
OUTPUT=$OUTPUT
BASE=$BASE
CONTAINER=$CONTAINER
IMAGE=$IMAGE
EOF

cat > "$BASE/docker-compose.yml" <<EOF
# ps5-lz4: generated by nas-lz4/install.sh
services:
  ps5-lz4:
    image: $IMAGE
    container_name: $CONTAINER
    restart: unless-stopped
    init: true
    network_mode: none
    environment:
      PS5LZ4_HOST_LIBRARY: "$LIBRARY"
      PS5LZ4_HOST_OUTPUT: "$OUTPUT"
      PS5LZ4_LEVEL: "$LEVEL"
      TZ: "$TZ_NAME"
    volumes:
      - "$LIBRARY:/library:ro"
      - "$OUTPUT:/output"
      - "$BASE/state:/state"
      - "$BASE/logs:/state/logs"
      - "$BASE/reports:/state/reports"
EOF

install -m 755 "$REPO/nas-lz4/lz4-ps5.sh" "$BASE/lz4-ps5.sh"

say "Building $IMAGE (log: $BASE/logs/build.log)"
if ! docker build -t "$IMAGE" -f "$REPO/nas-lz4/Dockerfile" "$REPO" > "$BASE/logs/build.log" 2>&1; then
  tail -20 "$BASE/logs/build.log"
  die "docker build failed; see $BASE/logs/build.log"
fi
ok "image built"

say "Starting container $CONTAINER"
if [ -n "$existing" ]; then docker rm -f "$CONTAINER" >/dev/null; fi
if [ -n "$COMPOSE" ]; then
  (cd "$BASE" && $COMPOSE -p ps5-lz4 up -d)
else
  docker run -d --name "$CONTAINER" --restart unless-stopped --init --network none \
    -e PS5LZ4_HOST_LIBRARY="$LIBRARY" -e PS5LZ4_HOST_OUTPUT="$OUTPUT" \
    -e PS5LZ4_LEVEL="$LEVEL" -e TZ="$TZ_NAME" \
    -v "$LIBRARY:/library:ro" -v "$OUTPUT:/output" -v "$BASE/state:/state" \
    -v "$BASE/logs:/state/logs" -v "$BASE/reports:/state/reports" \
    "$IMAGE" >/dev/null
fi
sleep 2
[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER")" = true ] || die "container did not start"
ok "container running"

say "Self-check"
"$BASE/lz4-ps5.sh" doctor
say "Library"
"$BASE/lz4-ps5.sh" scan

cat <<EOF

Installed. Next steps (as $NAS_USER or root):
  cd $BASE
  ./lz4-ps5.sh scan --check        # which games can use LZ4 packs
  ./lz4-ps5.sh start <# or name>   # ONE game first, runs in the background
  ./lz4-ps5.sh status              # progress
  ./lz4-ps5.sh report              # sizes and savings
EOF
