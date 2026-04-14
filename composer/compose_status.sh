#!/usr/bin/env bash
set -euo pipefail

# THIS IS MUSIC: Master compose_status.sh
# Checks status of services across all VMs

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

status_host () {
  local label="$1"
  local host="$2"
  local status_cmd="$3"

  echo
  echo "========== ${label} (${host}) =========="

  local user
  user="$(pick_user "$host" || true)"

  if [[ -z "${user}" ]]; then
    echo "not reachable"
    return 1
  fi

  echo "Using user: ${user}"
  ssh_run_user "$user" "$host" "$status_cmd" || true
  return 0
}

LOCAL_IP="$(tailscale ip -4 2>/dev/null | head -n1 || true)"

status_host "Database" "$DB_HOST" "$DB_STATUS" || true

if [[ -n "${RMQ_HOST:-}" && -n "${LOCAL_IP}" && "$LOCAL_IP" == "$RMQ_HOST" ]]; then
  echo
  echo "========== RabbitMQ (${RMQ_HOST}) =========="
  echo "Running locally"
  bash -lc "$RMQ_STATUS" || true
else
  status_host "RabbitMQ" "$RMQ_HOST" "$RMQ_STATUS" || true
fi

status_host "Backend-FE" "$BE_FE_HOST" "$BE_FE_STATUS" || true
status_host "Backend-DB" "$BE_DB_HOST" "$BE_DB_STATUS" || true
status_host "Frontend" "$FE_HOST" "$FE_STATUS" || true

echo
echo "compose_status complete"