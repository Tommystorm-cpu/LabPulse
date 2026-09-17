#!/usr/bin/env bash

# Shared helpers for the real-Pi hardware fault-injection scripts. This file is
# sourced by the X1200 and DHT11 wrappers; it is not an operator entry point.

fault_die() {
  echo "ERROR: $*" >&2
  exit 1
}

fault_live_dir() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
  printf '%s\n' "${LABPULSE_LIVE_DIR:-$script_dir}"
}

fault_load_docker_command() {
  DOCKER_COMMAND=()
  if [ -n "${LABPULSE_DOCKER_COMMAND:-}" ]; then
    # Match the documented simple forms, such as "docker" and "sudo docker".
    read -r -a DOCKER_COMMAND <<<"$LABPULSE_DOCKER_COMMAND"
  elif [ "$(id -u)" -eq 0 ]; then
    DOCKER_COMMAND=(docker)
  elif command -v sudo >/dev/null 2>&1; then
    DOCKER_COMMAND=(sudo docker)
  else
    DOCKER_COMMAND=(docker)
  fi
}

fault_require_live_install() {
  PROJECT_DIR="$(fault_live_dir)"
  COMPOSE_FILE="$PROJECT_DIR/compose.yaml"
  LIVE_CONFIG="$PROJECT_DIR/config.yaml"
  HOST_PYTHON="$PROJECT_DIR/.venv/bin/python"

  [ -f "$COMPOSE_FILE" ] ||
    fault_die "Missing $COMPOSE_FILE. Run 'labpulse setup' first."
  [ -f "$LIVE_CONFIG" ] ||
    fault_die "Missing $LIVE_CONFIG. Run 'labpulse setup' first."
  [ -x "$HOST_PYTHON" ] ||
    fault_die "Missing $HOST_PYTHON. Run 'labpulse setup' first."

  fault_load_docker_command
  command -v "${DOCKER_COMMAND[0]}" >/dev/null 2>&1 ||
    fault_die "Cannot run ${DOCKER_COMMAND[0]}. Set LABPULSE_DOCKER_COMMAND if needed."
}

fault_compose() {
  "${DOCKER_COMMAND[@]}" compose \
    --project-directory "$PROJECT_DIR" \
    "$@"
}

fault_apply_override() {
  local override_file="$1"
  local compose_service="$2"

  if ! fault_compose \
    -f "$COMPOSE_FILE" \
    -f "$override_file" \
    config --quiet; then
    rm -f "$override_file"
    fault_die \
      "Docker Compose rejected the fault override. LabPulse requires a Compose " \
      "version supporting the !reset/!override tags (2.24.4 or newer)."
  fi

  echo "Recreating $compose_service with the test fault active..."
  if ! fault_compose \
    -f "$COMPOSE_FILE" \
    -f "$override_file" \
    up -d --no-deps --force-recreate "$compose_service"; then
    fault_die \
      "Could not recreate $compose_service. The normal Compose file was not changed; " \
      "run this script's restore command before continuing."
  fi

  echo
  echo "Fault active. The generated compose.yaml and host device permissions are unchanged."
  echo "Keep this terminal available and run the matching restore command when finished."
  echo
  fault_compose -f "$COMPOSE_FILE" ps "$compose_service"
}

fault_restore_service() {
  local override_file="$1"
  local compose_service="$2"
  local settle_seconds="${3:-0}"

  echo "Recreating $compose_service from the normal generated Compose definition..."
  if [ "$settle_seconds" != "0" ]; then
    echo "Stopping $compose_service and allowing hardware resources to settle..."
    fault_compose -f "$COMPOSE_FILE" stop "$compose_service"
    sleep "$settle_seconds"
  fi
  fault_compose \
    -f "$COMPOSE_FILE" \
    up -d --no-deps --force-recreate "$compose_service"
  rm -f "$override_file"

  echo
  echo "Normal hardware access restored."
  fault_compose -f "$COMPOSE_FILE" ps "$compose_service"
}

fault_show_status() {
  local override_file="$1"
  local compose_service="$2"

  if [ -f "$override_file" ]; then
    echo "Fault override file present: $override_file"
    echo "The fault remains active unless the service has since been recreated without it."
  else
    echo "No fault override file is present."
  fi
  echo
  fault_compose -f "$COMPOSE_FILE" ps "$compose_service"
  echo
  fault_compose -f "$COMPOSE_FILE" logs --tail 25 "$compose_service"
}
