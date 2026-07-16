#!/usr/bin/env bash
set -euo pipefail

# Interactively characterize the voltage and state-of-charge transitions of the
# live LabPulse UPS. The script only reads MQTT; it never controls mains power.

SERVICE="ups_monitor"
TRIALS=3
BASELINE_SECONDS=30
OUTAGE_SECONDS=60
RECOVERY_SECONDS=120
SETTLING_SECONDS=300
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage: ./characterize_ups.sh [options]

Interactively record controlled UPS mains-off/on trials and calculate candidate
voltage-transition and battery-charge recovery settings.

Options:
  --service NAME       UPS service name. Default: ups_monitor
  --trials N           Number of outage/recovery trials. Default: 3
  --baseline SECONDS   Mains-on baseline before each trial. Default: 30
  --outage SECONDS     Requested disconnected time per trial. Default: 60
  --recovery SECONDS   Observation after restoring mains. Default: 120
  --settling SECONDS   Final post-test mains-on observation. Default: 300
  --project-dir DIR    Live Compose directory. Default: script directory
  --quick              One 20s baseline, 30s outage, and 60s recovery
  -h, --help           Show this help

The script requires the live Mosquitto Compose service and uses sudo docker.
It never switches mains itself: you perform each safe disconnection/reconnection
and press Enter to timestamp it.
EOF
}

require_positive_integer() {
  local name="$1"
  local value="$2"
  if ! [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
    echo "$name must be a positive integer, got: $value" >&2
    exit 2
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --service) SERVICE="$2"; shift 2 ;;
    --trials) TRIALS="$2"; shift 2 ;;
    --baseline) BASELINE_SECONDS="$2"; shift 2 ;;
    --outage) OUTAGE_SECONDS="$2"; shift 2 ;;
    --recovery) RECOVERY_SECONDS="$2"; shift 2 ;;
    --settling) SETTLING_SECONDS="$2"; shift 2 ;;
    --project-dir) PROJECT_DIR="$2"; shift 2 ;;
    --quick)
      TRIALS=1
      BASELINE_SECONDS=20
      OUTAGE_SECONDS=30
      RECOVERY_SECONDS=60
      SETTLING_SECONDS=120
      shift
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

require_positive_integer "--trials" "$TRIALS"
require_positive_integer "--baseline" "$BASELINE_SECONDS"
require_positive_integer "--outage" "$OUTAGE_SECONDS"
require_positive_integer "--recovery" "$RECOVERY_SECONDS"
require_positive_integer "--settling" "$SETTLING_SECONDS"

PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
if [ ! -f "$PROJECT_DIR/compose.yaml" ]; then
  echo "No compose.yaml found in $PROJECT_DIR" >&2
  echo "Run this copy from the live ~/labpulse-ha directory or use --project-dir." >&2
  exit 1
fi

for command in sudo docker python3; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Required command is missing: $command" >&2
    exit 1
  fi
done

cd "$PROJECT_DIR"
sudo -v
if ! sudo docker compose ps --status running mosquitto | grep -q 'mosquitto\|labpulse-mqtt'; then
  echo "The Mosquitto Compose service is not running." >&2
  sudo docker compose ps mosquitto >&2 || true
  exit 1
fi

RUN_ID="$(date +%Y%m%d-%H%M%S)"
OUTPUT_DIR="$PROJECT_DIR/ups-characterisation"
DATA_FILE="$OUTPUT_DIR/$RUN_ID-readings.tsv"
EVENT_FILE="$OUTPUT_DIR/$RUN_ID-events.tsv"
mkdir -p "$OUTPUT_DIR"
: > "$DATA_FILE"
: > "$EVENT_FILE"

VOLTAGE_TOPIC="home/sensor/$SERVICE/voltage/state"
CHARGE_TOPIC="home/sensor/$SERVICE/battery_level/state"
SUBSCRIBER_PID=""

cleanup() {
  if [ -n "$SUBSCRIBER_PID" ] && kill -0 "$SUBSCRIBER_PID" 2>/dev/null; then
    kill "$SUBSCRIBER_PID" 2>/dev/null || true
    wait "$SUBSCRIBER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

record_event() {
  local trial="$1"
  local event="$2"
  printf '%s\t%s\t%s\n' "$(date +%s.%N)" "$trial" "$event" >> "$EVENT_FILE"
}

countdown() {
  local seconds="$1"
  local label="$2"
  local remaining
  for ((remaining=seconds; remaining>0; remaining--)); do
    printf '\r%-55s %4ss remaining' "$label" "$remaining"
    sleep 1
  done
  printf '\r%-55s done               \n' "$label"
}

echo
echo "LabPulse UPS characterization"
echo "================================"
echo "Trials:             $TRIALS"
echo "Baseline per trial: ${BASELINE_SECONDS}s"
echo "Outage per trial:   ${OUTAGE_SECONDS}s"
echo "Recovery per trial: ${RECOVERY_SECONDS}s"
echo "Final settling:     ${SETTLING_SECONDS}s"
echo "Voltage topic:      $VOLTAGE_TOPIC"
echo "Charge topic:       $CHARGE_TOPIC"
echo
echo "Safety: use only the UPS's normal plug or an approved mains switch."
echo "Do not open equipment or handle exposed mains wiring. Stop if the"
echo "connected equipment or battery behaves unexpectedly."
echo
read -r -p "Confirm mains is currently connected, then press Enter to begin. "

# Prefix every MQTT message with the Pi's receipt timestamp. Exact topics have
# numeric payloads without spaces, so the two-field reader is intentional.
(
  sudo docker compose exec -T mosquitto \
    mosquitto_sub -h 127.0.0.1 \
      -t "$VOLTAGE_TOPIC" \
      -t "$CHARGE_TOPIC" \
      -v |
  while read -r topic payload; do
    if [ -n "${topic:-}" ] && [ -n "${payload:-}" ]; then
      printf '%s\t%s\t%s\n' "$(date +%s.%N)" "$topic" "$payload"
    fi
  done
) >> "$DATA_FILE" &
SUBSCRIBER_PID=$!

echo "Waiting for live voltage and charge telemetry..."
telemetry_ready=0
for _ in $(seq 1 20); do
  if grep -q "$VOLTAGE_TOPIC" "$DATA_FILE" && grep -q "$CHARGE_TOPIC" "$DATA_FILE"; then
    telemetry_ready=1
    break
  fi
  sleep 1
done
if [ "$telemetry_ready" -ne 1 ]; then
  echo "No complete UPS telemetry arrived within 20 seconds." >&2
  echo "Check the service and topics, then retry. Partial data: $DATA_FILE" >&2
  exit 1
fi
echo "Telemetry received."

for ((trial=1; trial<=TRIALS; trial++)); do
  echo
  echo "Trial $trial of $TRIALS"
  echo "------------------------------"
  record_event "$trial" "baseline_start"
  countdown "$BASELINE_SECONDS" "Collecting mains-on baseline"

  echo
  read -r -p "Disconnect UPS mains safely, then press Enter immediately. "
  record_event "$trial" "mains_off"
  countdown "$OUTAGE_SECONDS" "Collecting mains-disconnected readings"

  echo
  read -r -p "Restore UPS mains safely, then press Enter immediately. "
  record_event "$trial" "mains_on"
  countdown "$RECOVERY_SECONDS" "Collecting recovery readings"
  record_event "$trial" "trial_end"
done

echo
echo "All controlled trials are complete. Keep mains connected while the script"
echo "checks for delayed charger-settling transitions."
record_event "$TRIALS" "settling_start"
countdown "$SETTLING_SECONDS" "Collecting final mains-on settling baseline"
record_event "$TRIALS" "settling_end"

sleep 2
cleanup
SUBSCRIBER_PID=""

python3 - "$DATA_FILE" "$EVENT_FILE" "$SERVICE" <<'PY'
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from statistics import median
import math
import sys


data_path = Path(sys.argv[1])
event_path = Path(sys.argv[2])
service = sys.argv[3]
voltage_topic = f"home/sensor/{service}/voltage/state"
charge_topic = f"home/sensor/{service}/battery_level/state"


def load_samples() -> dict[str, list[tuple[float, float]]]:
    """Load numeric MQTT samples grouped by topic."""

    result: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for line in data_path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        try:
            timestamp = float(parts[0])
            value = float(parts[2])
        except ValueError:
            continue
        result[parts[1]].append((timestamp, value))
    return result


def load_events() -> dict[int, dict[str, float]]:
    """Load phase markers grouped by trial number."""

    result: dict[int, dict[str, float]] = defaultdict(dict)
    for line in event_path.read_text(encoding="utf-8").splitlines():
        timestamp, trial, event = line.split("\t")
        result[int(trial)][event] = float(timestamp)
    return result


def between(
    series: list[tuple[float, float]], start: float, end: float
) -> list[tuple[float, float]]:
    """Return samples in a half-open time interval."""

    return [(timestamp, value) for timestamp, value in series if start <= timestamp < end]


def med(series: list[tuple[float, float]]) -> float:
    """Return a series median or NaN when the interval is empty."""

    return median(value for _, value in series) if series else math.nan


def nearest(
    series: list[tuple[float, float]], target: float, tolerance: float = 5.0
) -> float:
    """Return the value nearest a requested timestamp within tolerance."""

    if not series:
        return math.nan
    timestamp, value = min(series, key=lambda item: abs(item[0] - target))
    return value if abs(timestamp - target) <= tolerance else math.nan


def extrema_change(
    series: list[tuple[float, float]], window: float
) -> tuple[float, float]:
    """Return largest fall and rise against earlier samples in a time window."""

    prior: deque[tuple[float, float]] = deque()
    largest_fall = 0.0
    largest_rise = 0.0
    for timestamp, value in series:
        while prior and timestamp - prior[0][0] > window:
            prior.popleft()
        if prior:
            values = [sample for _, sample in prior]
            largest_fall = max(largest_fall, max(values) - value)
            largest_rise = max(largest_rise, value - min(values))
        prior.append((timestamp, value))
    return largest_fall, largest_rise


def fmt(value: float, digits: int = 3, suffix: str = "") -> str:
    """Format an optional numeric measurement for terminal output."""

    return "n/a" if math.isnan(value) else f"{value:.{digits}f}{suffix}"


samples = load_samples()
events = load_events()
voltage = samples.get(voltage_topic, [])
charge = samples.get(charge_topic, [])
if not voltage or not charge:
    raise SystemExit("Analysis failed: voltage or charge samples are missing")

normal_falls: list[float] = []
normal_rises: list[float] = []
outage_drops: list[float] = []
unplugged_rises: list[float] = []
recovery_rises: list[float] = []
charge_during_outage: list[float] = []
charge_after_recovery: list[float] = []
rebound_times: list[float] = []

print("\nUPS characterization results")
print("=" * 78)
for trial in sorted(events):
    phase = events[trial]
    required = {"baseline_start", "mains_off", "mains_on", "trial_end"}
    if not required.issubset(phase):
        print(f"Trial {trial}: incomplete event markers; skipped")
        continue

    baseline_start = phase["baseline_start"]
    mains_off = phase["mains_off"]
    mains_on = phase["mains_on"]
    trial_end = phase["trial_end"]
    baseline_v = between(voltage, baseline_start, mains_off)
    pre_v = between(voltage, max(baseline_start, mains_off - 10), mains_off)
    outage_v = between(voltage, mains_off, mains_on)
    first_outage_v = between(voltage, mains_off, min(mains_on, mains_off + 10))
    steady_outage_v = between(voltage, max(mains_off, mains_on - 10), mains_on)
    first_recovery_v = between(voltage, mains_on, min(trial_end, mains_on + 10))
    recovery_v = between(voltage, mains_on, trial_end)

    pre_voltage = med(pre_v)
    minimum_voltage = min((value for _, value in first_outage_v), default=math.nan)
    drop = pre_voltage - minimum_voltage
    steady_voltage = med(steady_outage_v)
    recovery_peak = max((value for _, value in first_recovery_v), default=math.nan)
    recovery_rise = recovery_peak - steady_voltage
    normal_fall, normal_rise = extrema_change(baseline_v, 5.0)
    _, unplugged_rise = extrema_change(outage_v, 5.0)
    normal_falls.append(normal_fall)
    normal_rises.append(normal_rise)
    settling_fall = math.nan
    settling_rise = math.nan
    if "settling_start" in phase and "settling_end" in phase:
        settling_v = between(
            voltage,
            phase["settling_start"],
            phase["settling_end"],
        )
        settling_fall, settling_rise = extrema_change(settling_v, 5.0)
        normal_falls.append(settling_fall)
        normal_rises.append(settling_rise)
    if not math.isnan(drop):
        outage_drops.append(drop)
    unplugged_rises.append(unplugged_rise)
    if not math.isnan(recovery_rise):
        recovery_rises.append(recovery_rise)

    if first_outage_v:
        minimum_time, _ = min(first_outage_v, key=lambda item: item[1])
        # Characterize the immediate electrochemical rebound, not a later
        # random high sample near the end of a long outage.
        rebound_end = min(mains_on, minimum_time + 30)
        samples_after_minimum = [
            item for item in outage_v if minimum_time <= item[0] <= rebound_end
        ]
        if samples_after_minimum:
            rebound_time, _ = max(samples_after_minimum, key=lambda item: item[1])
            rebound_times.append(max(0.0, rebound_time - mains_off))

    soc_off = nearest(charge, mains_off)
    soc_on = nearest(charge, mains_on)
    soc_end = nearest(charge, trial_end)
    outage_soc_delta = soc_on - soc_off
    recovery_soc_delta = soc_end - soc_on
    if not math.isnan(outage_soc_delta):
        charge_during_outage.append(outage_soc_delta)
    if not math.isnan(recovery_soc_delta):
        charge_after_recovery.append(recovery_soc_delta)

    soc_30 = nearest(charge, min(trial_end, mains_on + 30))
    soc_60 = nearest(charge, min(trial_end, mains_on + 60))
    soc_120 = nearest(charge, min(trial_end, mains_on + 120))

    print(f"\nTrial {trial}")
    print(
        f"  Voltage: pre {fmt(pre_voltage)} V | first-10s min {fmt(minimum_voltage)} V"
        f" | outage drop {fmt(drop)} V"
    )
    print(
        f"           unplugged steady {fmt(steady_voltage)} V | recovery peak"
        f" {fmt(recovery_peak)} V | recovery rise {fmt(recovery_rise)} V"
    )
    print(
        f"  Charge:  off {fmt(soc_off, 1, '%')} | on {fmt(soc_on, 1, '%')}"
        f" | end {fmt(soc_end, 1, '%')} | outage change {fmt(outage_soc_delta, 1, '%')}"
        f" | recovery change {fmt(recovery_soc_delta, 1, '%')}"
    )
    print(
        f"           after restore: +30s {fmt(soc_30, 1, '%')} |"
        f" +60s {fmt(soc_60, 1, '%')} | +120s {fmt(soc_120, 1, '%')}"
    )
    print(
        f"  Noise:   largest normal 5s fall {normal_fall:.3f} V |"
        f" normal 5s rise {normal_rise:.3f} V | unplugged 5s rise {unplugged_rise:.3f} V"
    )
    if not math.isnan(settling_fall):
        print(
            f"           final settling 5s fall {settling_fall:.3f} V |"
            f" final settling 5s rise {settling_rise:.3f} V"
        )

print("\nCandidate settings")
print("-" * 78)
max_normal_drop = max(normal_falls, default=math.nan)
min_outage_drop = min(outage_drops, default=math.nan)
if (
    not math.isnan(max_normal_drop)
    and not math.isnan(min_outage_drop)
    and min_outage_drop > max_normal_drop + 0.01
):
    midpoint = (max_normal_drop + min_outage_drop) / 2
    # Round upward to a centivolt so a tiny, unobserved charger-control step
    # cannot sit immediately above a mathematically exact midpoint.
    candidate = math.ceil(midpoint * 100) / 100
    print(
        f"  outage_drop_volts: {candidate:.3f}"
        f"  (normal max {max_normal_drop:.3f}, outage min {min_outage_drop:.3f})"
    )
else:
    print("  outage_drop_volts: no safe separation found; collect more trials")

max_unplugged_rise = max(unplugged_rises, default=math.nan)
min_recovery_rise = min(recovery_rises, default=math.nan)
if (
    not math.isnan(max_unplugged_rise)
    and not math.isnan(min_recovery_rise)
    and min_recovery_rise > max_unplugged_rise + 0.01
):
    candidate = (max_unplugged_rise + min_recovery_rise) / 2
    print(
        f"  recovery_rise_volts: {candidate:.3f}"
        f"  (unplugged max {max_unplugged_rise:.3f}, recovery min {min_recovery_rise:.3f})"
    )
else:
    print("  recovery_rise_volts: voltage rebound overlaps recovery; require charge evidence")

if rebound_times:
    print(f"  recovery_lockout_seconds: {math.ceil(max(rebound_times) + 5):d}")
else:
    print("  recovery_lockout_seconds: n/a")

min_recovery_charge = min(charge_after_recovery, default=math.nan)
max_unplugged_charge = max(charge_during_outage, default=math.nan)
if (
    not math.isnan(min_recovery_charge)
    and not math.isnan(max_unplugged_charge)
    and min_recovery_charge >= 0.2
    and min_recovery_charge > max_unplugged_charge + 0.1
):
    candidate = max(0.2, round((max_unplugged_charge + min_recovery_charge) / 2, 1))
    print(f"  recovery_charge_rise_percent: {candidate:.1f}")
else:
    print("  recovery_charge_rise_percent: no repeatable positive separation yet")

print("  transition_window_seconds: 5")
print("\nRaw evidence")
print(f"  readings: {data_path}")
print(f"  events:   {event_path}")
print("\nTreat these as initial candidates. More trials and a second battery level")
print("increase confidence before enabling real notifications.")
PY

echo
echo "Characterization complete."
