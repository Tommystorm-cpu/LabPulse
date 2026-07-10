#!/usr/bin/env bash
set -euo pipefail

# Fake serial devices live in /tmp by default so they are easy to mount into the
# LabPulse Python containers and easy to discard after testing.
SIM_DIR="${LABPULSE_FAKE_SERIAL_DIR:-/tmp/labpulse-fake-serial}"
INTERVAL="${LABPULSE_FAKE_SERIAL_INTERVAL:-1}"
SCENARIO_FILE="${LABPULSE_FAKE_SERIAL_SCENARIO_FILE:-}"
SCENARIOS=()

# Track background socat/writer processes so Ctrl+C can clean them up.
SOCAT_PIDS=()
WRITER_PIDS=()

usage() {
  cat <<'EOF'
Usage: ./simulate_arduinos.sh [--dir PATH] [--interval SECONDS] [--scenario SERVICE.READING=STATE] [--scenario-file PATH]

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
  LABPULSE_FAKE_SERIAL_SCENARIO_FILE=/tmp/my-scenarios.txt ./simulate_arduinos.sh

Alarm test scenarios:
  --scenario pressure_monitor.pressure=danger-low
  --scenario pressure_monitor.pressure=recover
  --scenario pump_room.flow1=danger-low
  --scenario pump_room.temp0=danger-high
  --scenario turbo_pump.flow2=recover
  --scenario pump_room.flow1=stale

Scenario states:
  normal       emit changing healthy values
  recover      alias for normal, useful after a danger test
  danger-low   emit changing low but valid values
  danger-high  emit changing high but valid values
  stale        emit one valid constant value so Home Assistant last_updated ages

Scenarios affect emitted Arduino values only. Home Assistant still decides the
alarm state from its editable helpers, modes, history window, and recovery time.

Scenarios are read live from:
  /tmp/labpulse-fake-serial/scenarios.txt

Edit that file while the simulator is running to change values without
recreating the fake serial devices. `--scenario` seeds the file at startup.

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
    --scenario)
      SCENARIOS+=("$2")
      shift 2
      ;;
    --scenario-file)
      SCENARIO_FILE="$2"
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

if [ -z "$SCENARIO_FILE" ]; then
  SCENARIO_FILE="$SIM_DIR/scenarios.txt"
fi

trim_scenario_line() {
  local value="$1"

  value="${value%%#*}"
  value="${value//$'\r'/}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s\n' "$value"
}

scenario_state() {
  local service="$1"
  local reading="$2"
  local wanted="${service}.${reading}"
  local scenario
  local normalized

  if [ -f "$SCENARIO_FILE" ]; then
    while IFS= read -r scenario || [ -n "$scenario" ]; do
      normalized="$(trim_scenario_line "$scenario")"
      if [ -n "$normalized" ] && [ "${normalized%%=*}" = "$wanted" ]; then
        printf '%s\n' "${normalized#*=}"
        return
      fi
    done < "$SCENARIO_FILE"
  else
    for scenario in "${SCENARIOS[@]}"; do
      if [ "${scenario%%=*}" = "$wanted" ]; then
        printf '%s\n' "${scenario#*=}"
        return
      fi
    done
  fi

  printf 'random\n'
}

validate_scenario_state() {
  local state="$1"

  case "$state" in
    random|normal|recover|danger-low|danger-high|stale)
      return
      ;;
    *)
      echo "Unknown scenario state: $state" >&2
      echo "Expected one of: normal, recover, danger-low, danger-high, stale" >&2
      exit 1
      ;;
  esac
}

validate_scenarios() {
  local scenario
  local normalized

  for scenario in "${SCENARIOS[@]}"; do
    validate_scenario_entry "$scenario"
  done

  if [ -f "$SCENARIO_FILE" ]; then
    while IFS= read -r scenario || [ -n "$scenario" ]; do
      normalized="$(trim_scenario_line "$scenario")"
      if [ -n "$normalized" ]; then
        validate_scenario_entry "$normalized"
      fi
    done < "$SCENARIO_FILE"
  fi
}

validate_scenario_entry() {
  local scenario="$1"
  local target
  local state

  if [[ "$scenario" != *=* ]]; then
    echo "Invalid scenario: $scenario" >&2
    echo "Use SERVICE.READING=STATE, for example pump_room.flow1=danger-low" >&2
    exit 1
  fi

  target="${scenario%%=*}"
  state="${scenario#*=}"
  validate_scenario_state "$state"

  case "$target" in
    pressure_monitor.pressure|pump_room.flow1|pump_room.flow2|pump_room.temp0|pump_room.temp1|pump_room.temp2|pump_room.temp3|turbo_pump.flow1|turbo_pump.flow2|turbo_pump.temp0|turbo_pump.temp1|turbo_pump.temp2|turbo_pump.temp3)
      ;;
    *)
      echo "Unsupported scenario target: $target" >&2
      echo "Supported examples: pressure_monitor.pressure, pump_room.flow1, turbo_pump.temp0" >&2
      exit 1
      ;;
  esac
}

prepare_scenario_file() {
  mkdir -p "$(dirname "$SCENARIO_FILE")"

  if [ "${#SCENARIOS[@]}" -gt 0 ]; then
    printf '%s\n' "${SCENARIOS[@]}" > "$SCENARIO_FILE"
    return
  fi

  if [ ! -e "$SCENARIO_FILE" ]; then
    cat > "$SCENARIO_FILE" <<'EOF'
# LabPulse fake Arduino live scenarios.
# Edit while simulate_arduinos.sh is running.
# Examples:
# pump_room.flow1=danger-low
# pump_room.flow1=recover
# pump_room.flow1=stale
EOF
  fi
}

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

scenario_hundredths() {
  local state="$1"
  local normal="$2"
  local low="$3"
  local high="$4"

  validate_scenario_state "$state"

  case "$state" in
    normal|recover)
      random_hundredths "$normal" "$((normal + 25))"
      ;;
    danger-low)
      random_hundredths 5 "$low"
      ;;
    danger-high)
      random_hundredths "$high" "$((high + 1000))"
      ;;
    stale)
      random_hundredths "$normal" "$normal"
      ;;
    random)
      random_hundredths "$normal" "$normal"
      ;;
  esac
}

scenario_tenths() {
  local state="$1"
  local normal="$2"
  local low="$3"
  local high="$4"

  validate_scenario_state "$state"

  case "$state" in
    normal|recover)
      random_tenths "$((normal - 5))" "$((normal + 5))"
      ;;
    danger-low)
      random_tenths "$low" "$((low + 5))"
      ;;
    danger-high)
      random_tenths "$high" "$((high + 10))"
      ;;
    stale)
      random_tenths "$normal" "$normal"
      ;;
    random)
      random_tenths "$normal" "$normal"
      ;;
  esac
}

scenario_pressure_raw() {
  local state="$1"
  local value

  validate_scenario_state "$state"

  case "$state" in
    normal|recover)
      value=$((1200 + RANDOM % 51))
      printf '0.%04d\n' "$value"
      ;;
    danger-low)
      value=$((500 + RANDOM % 91))
      printf '0.%04d\n' "$value"
      ;;
    danger-high)
      printf '%d.%04d\n' "$((120 + RANDOM % 2))" "$((RANDOM % 10000))"
      ;;
    stale)
      printf '0.1200\n'
      ;;
    random)
      random_pressure_raw
      ;;
  esac
}

flow_value() {
  local service="$1"
  local reading="$2"
  local state

  state="$(scenario_state "$service" "$reading")"
  if [ "$state" = "random" ]; then
    random_hundredths 150 550
    return
  fi

  scenario_hundredths "$state" 250 20 120000
}

turbo_flow_value() {
  local reading="$1"
  local state

  state="$(scenario_state "turbo_pump" "$reading")"
  if [ "$state" = "random" ]; then
    random_hundredths 150 420
    return
  fi

  scenario_hundredths "$state" 250 20 120000
}

temperature_value() {
  local service="$1"
  local reading="$2"
  local state

  state="$(scenario_state "$service" "$reading")"
  if [ "$state" = "random" ]; then
    random_tenths 185 235
    return
  fi

  scenario_tenths "$state" 220 0 600
}

turbo_temperature_value() {
  local reading="$1"
  local state

  state="$(scenario_state "turbo_pump" "$reading")"
  if [ "$state" = "random" ]; then
    random_tenths 205 260
    return
  fi

  scenario_tenths "$state" 220 0 600
}

# Pressure Arduino emits raw MPa-looking values; Python scales them to bar.
random_pressure_raw() {
  local value=$((1200 + RANDOM % 101))
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
  local state

  while true; do
    state="$(scenario_state "pressure_monitor" "pressure")"
    printf '%s\n' "$(scenario_pressure_raw "$state")" > "$writer"
    sleep "$INTERVAL"
  done
}

# Pump room sketch: emits flow, temperature, and room/pressure readings as
# separate lines, matching the parser's multi-format behavior.
write_pump_room() {
  local writer="$SIM_DIR/pump_room_writer"

  while true; do
    printf 'Flow1: %s L/min | Flow2: %s L/min\n' \
      "$(flow_value "pump_room" "flow1")" \
      "$(flow_value "pump_room" "flow2")" \
      > "$writer"

    printf 'Temp0: %sC  Temp1: %sC  Temp2: %sC  Temp3: %sC  \n' \
      "$(temperature_value "pump_room" "temp0")" \
      "$(temperature_value "pump_room" "temp1")" \
      "$(temperature_value "pump_room" "temp2")" \
      "$(temperature_value "pump_room" "temp3")" \
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
      "$(turbo_flow_value "flow1")" \
      "$(turbo_flow_value "flow2")" \
      > "$writer"

    printf 'Temp0: %sC  Temp1: %sC  Temp2: %sC  Temp3: %sC  \n' \
      "$(turbo_temperature_value "temp0")" \
      "$(turbo_temperature_value "temp1")" \
      "$(turbo_temperature_value "temp2")" \
      "$(turbo_temperature_value "temp3")" \
      > "$writer"

    sleep "$INTERVAL"
  done
}

require_command socat

mkdir -p "$SIM_DIR"
prepare_scenario_file
validate_scenarios

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

Live scenario control file:
  $SCENARIO_FILE

Change scenarios without restarting, for example:
  printf 'pump_room.flow1=danger-low\n' > "$SCENARIO_FILE"
  printf 'pump_room.flow1=recover\n' > "$SCENARIO_FILE"

Press Ctrl+C to stop the simulation.
EOF

printf '\nInitial alarm test scenarios:\n'
grep -v '^[[:space:]]*#' "$SCENARIO_FILE" | grep -v '^[[:space:]]*$' | sed 's/^/  /' || true

wait
