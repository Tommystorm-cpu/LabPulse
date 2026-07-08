#!/usr/bin/env bash
set -euo pipefail

# Fake serial devices live in /tmp by default so they are easy to mount into the
# LabPulse Python containers and easy to discard after testing.
SIM_DIR="${LABPULSE_FAKE_SERIAL_DIR:-/tmp/labpulse-fake-serial}"
INTERVAL="${LABPULSE_FAKE_SERIAL_INTERVAL:-1}"

# Track background socat/writer processes so Ctrl+C can clean them up.
SOCAT_PIDS=()
WRITER_PIDS=()

usage() {
  cat <<'EOF'
Usage: ./simulate_arduinos.sh [--dir PATH] [--interval SECONDS]

Creates three fake serial devices using socat and writes serial readings that
match the Arduino sketches in this repository until stopped with Ctrl+C.

Default fake device paths:
  /tmp/labpulse-fake-serial/pressure
  /tmp/labpulse-fake-serial/pump_room
  /tmp/labpulse-fake-serial/turbo_pump

Matching writer paths:
  /tmp/labpulse-fake-serial/pressure_writer
  /tmp/labpulse-fake-serial/pump_room_writer
  /tmp/labpulse-fake-serial/turbo_pump_writer

Config override:
  LABPULSE_FAKE_SERIAL_DIR=/tmp/my-fake-serial ./simulate_arduinos.sh
  LABPULSE_FAKE_SERIAL_INTERVAL=2 ./simulate_arduinos.sh

Requires:
  socat
EOF
}

# Simple option parser; environment variables are also supported for common
# repeatable test settings.
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dir)
      SIM_DIR="$2"
      shift 2
      ;;
    --interval)
      INTERVAL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

# Fail early with a helpful install hint if socat is not available.
require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    echo "Install it with: sudo apt install $1" >&2
    exit 1
  fi
}

# Remove fake serial links and stop background writers/socat pairs on exit.
cleanup() {
  set +e

  for pid in "${WRITER_PIDS[@]}"; do
    kill "$pid" >/dev/null 2>&1
  done

  for pid in "${SOCAT_PIDS[@]}"; do
    kill "$pid" >/dev/null 2>&1
  done

  rm -f \
    "$SIM_DIR/pressure" \
    "$SIM_DIR/pressure_writer" \
    "$SIM_DIR/pump_room" \
    "$SIM_DIR/pump_room_writer" \
    "$SIM_DIR/turbo_pump" \
    "$SIM_DIR/turbo_pump_writer"

  echo
  echo "Stopped fake Arduino serial devices."
}

trap cleanup EXIT INT TERM

# Numeric helpers generate values in the same decimal style as the Arduino
# sketches, keeping parser tests realistic.
random_tenths() {
  local min="$1"
  local max="$2"
  local value=$((min + RANDOM % (max - min + 1)))
  printf '%d.%d' "$((value / 10))" "$((value % 10))"
}

random_hundredths() {
  local min="$1"
  local max="$2"
  local value=$((min + RANDOM % (max - min + 1)))
  printf '%d.%02d' "$((value / 100))" "$((value % 100))"
}

# Pressure Arduino emits raw MPa-looking values; Python scales them to bar.
random_pressure_raw() {
  local value=$((950 + RANDOM % 151))
  printf '0.%04d' "$value"
}

# Create a linked pseudo-terminal pair. LabPulse reads from <name>; this
# simulator writes to <name>_writer.
start_pair() {
  local name="$1"
  local read_link="$SIM_DIR/$name"
  local write_link="$SIM_DIR/${name}_writer"

  rm -f "$read_link" "$write_link"

  socat -d -d \
    "pty,raw,echo=0,link=$read_link" \
    "pty,raw,echo=0,link=$write_link" \
    >/tmp/labpulse-socat-"$name".log 2>&1 &

  SOCAT_PIDS+=("$!")

  for _ in $(seq 1 50); do
    if [ -e "$read_link" ] && [ -e "$write_link" ]; then
      return
    fi
    sleep 0.1
  done

  echo "Timed out creating fake serial pair: $name" >&2
  echo "socat log: /tmp/labpulse-socat-$name.log" >&2
  exit 1
}

# Compressed-air sketch: one numeric value per line.
write_pressure() {
  local writer="$SIM_DIR/pressure_writer"

  while true; do
    printf '%s\n' "$(random_pressure_raw)" > "$writer"
    sleep "$INTERVAL"
  done
}

# Pump room sketch: emits flow, temperature, and room/pressure readings as
# separate lines, matching the parser's multi-format behavior.
write_pump_room() {
  local writer="$SIM_DIR/pump_room_writer"

  while true; do
    printf 'Flow1: %s L/min | Flow2: %s L/min\n' \
      "$(random_hundredths 150 550)" \
      "$(random_hundredths 150 550)" \
      > "$writer"

    printf 'Temp0: %sC  Temp1: %sC  Temp2: %sC  Temp3: %sC  \n' \
      "$(random_tenths 185 235)" \
      "$(random_tenths 185 235)" \
      "$(random_tenths 185 235)" \
      "$(random_tenths 185 235)" \
      > "$writer"

    printf 'RoomTemp: %sC | RoomHum: %s%% | Press1: %s bar | Press2: %s bar\n' \
      "$(random_tenths 185 245)" \
      "$(random_tenths 350 650)" \
      "$(random_hundredths 80 160)" \
      "$(random_hundredths 80 160)" \
      > "$writer"

    sleep "$INTERVAL"
  done
}

# Turbo pump sketch: emits flow and temperature readings in the combined style
# used by the current water parser.
write_turbo_pump() {
  local writer="$SIM_DIR/turbo_pump_writer"

  while true; do
    printf 'Flow1: %s L/min | Flow2: %s L/min' \
      "$(random_hundredths 150 420)" \
      "$(random_hundredths 150 420)" \
      > "$writer"

    printf 'Temp0: %sC  Temp1: %sC  Temp2: %sC  Temp3: %sC  \n' \
      "$(random_tenths 205 260)" \
      "$(random_tenths 205 260)" \
      "$(random_tenths 205 260)" \
      "$(random_tenths 205 260)" \
      > "$writer"

    sleep "$INTERVAL"
  done
}

require_command socat

mkdir -p "$SIM_DIR"

# Create all pseudo-serial devices before starting writers so containers can
# connect immediately.
start_pair pressure
start_pair pump_room
start_pair turbo_pump

write_pressure &
WRITER_PIDS+=("$!")

write_pump_room &
WRITER_PIDS+=("$!")

write_turbo_pump &
WRITER_PIDS+=("$!")

cat <<EOF
Fake Arduino serial devices are running.

Use these config.yaml serial_port values:

pressure_monitor:
  serial_port: "$SIM_DIR/pressure"

pump_room:
  serial_port: "$SIM_DIR/pump_room"

turbo_pump:
  serial_port: "$SIM_DIR/turbo_pump"

Writer links, for manual tests:
  $SIM_DIR/pressure_writer
  $SIM_DIR/pump_room_writer
  $SIM_DIR/turbo_pump_writer

Press Ctrl+C to stop the simulation.
EOF

wait
