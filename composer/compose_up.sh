#!/usr/bin/env bash
set -euo pipefail

# THIS IS MUSIC: Master compose_up.sh
# This will orchestrate startup across all of our VMs

source ./hosts.env

expand_path () {
  local p="$1"
  echo "${p/#\~/$HOME}"
}

SSH_KEY="$(expand_path "$SSH_KEY")"

ssh_ok_user () {
  local user="$1"
  local host="$2"

  ssh -o BatchMode=yes \
      -o StrictHostKeyChecking=no \
      -o ConnectTimeout=3 \
      -i "$SSH_KEY" "${user}@${host}" "echo ok" \
      >/dev/null 2>&1
}

ssh_run_user () {
  local user="$1"
  local host="$2"
  local cmd="$3"

  ssh -o StrictHostKeyChecking=no \
      -o ConnectTimeout=10 \
      -i "$SSH_KEY" "${user}@${host}" "$cmd"
}

pick_user () {
  local host="$1"
  local tried=()
  local candidates=()

  if [[ -n "${SSH_USER:-}" ]]; then
    candidates+=("$SSH_USER")
  fi

  candidates+=(daniel music musicdb meek)

  for u in "${candidates[@]}"; do
    if [[ " ${tried[*]} " == *" ${u} "* ]]; then
      continue
    fi
    tried+=("$u")

    if ssh_ok_user "$u" "$host"; then
      echo "$u"
      return 0
    fi
  done

  echo ""
  return 1
}

start_host () {
  local label="$1"
  local host="$2"
  local start_cmd="$3"

  echo
  echo "Starting ${label} (${host})"

  local user
  user="$(pick_user "$host" || true)"

  if [[ -z "${user}" ]]; then
    echo "  ${label} not reachable"
    return 1
  fi

  echo "  Using user: ${user}"
  ssh_run_user "$user" "$host" "$start_cmd" || true
  echo "  ${label} start command sent"
  return 0
}

# Local RMQ detection
LOCAL_IP="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
RMQ_LOCAL_STARTED=0

if [[ -n "${RMQ_HOST:-}" && -n "${LOCAL_IP}" && "$LOCAL_IP" == "$RMQ_HOST" ]]; then
  echo
  echo "Starting RabbitMQ locally"

  if [[ -f "$HOME/rabbitmq_composer.sh" ]]; then
    chmod +x "$HOME/rabbitmq_composer.sh" 2>/dev/null || true
    bash "$HOME/rabbitmq_composer.sh"
    RMQ_LOCAL_STARTED=1
  else
    echo "  rabbitmq_composer.sh not found"
  fi
fi

# Start order
start_host "Database" "$DB_HOST" "$DB_START" || true

if [[ "$RMQ_LOCAL_STARTED" -eq 1 ]]; then
  echo
  echo "RabbitMQ already started locally"
else
  start_host "RabbitMQ" "$RMQ_HOST" "$RMQ_START" || true
fi

start_host "Backend-FE" "$BE_FE_HOST" "$BE_FE_START" || true
start_host "Backend-DB" "$BE_DB_HOST" "$BE_DB_START" || true
start_host "Frontend" "$FE_HOST" "$FE_START" || true

echo
echo "compose_up complete"