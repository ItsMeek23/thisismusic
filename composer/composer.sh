#!/usr/bin/env bash
set -e
source ./hosts.env
SSH_KEY="${SSH_KEY/#\~/$HOME}"

run_remote() {
  local user="$1"
  local host="$2"
  local cmd="$3"
  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 -o ServerAliveInterval=10 -o ServerAliveCountMax=2 -i "$SSH_KEY" "$user@$host" "$cmd"
}

show_status() {
  local user="$1"
  local host="$2"
  local cmd="$3"
  local descriptor="$4"
  local result
  result=$(run_remote "$user" "$host" "$cmd" 2>/dev/null || echo "DOWN")
  echo "  $descriptor: $result"
}

start_if_needed() {
  local user="$1"
  local host="$2"
  local status_cmd="$3"
  local start_cmd="$4"
  local descriptor="$5"
  local current_status
  current_status=$(run_remote "$user" "$host" "$status_cmd" 2>/dev/null || echo "DOWN")
  if [ "$current_status" = "UP" ]; then
    echo "  $descriptor: Already UP"
  else
    echo "  $descriptor: Starting..."
    run_remote "$user" "$host" "$start_cmd" >/dev/null 2>&1 || true
    sleep 5
    local result
    result=$(run_remote "$user" "$host" "$status_cmd" 2>/dev/null || echo "DOWN")
    echo "  $descriptor: $result"
  fi
}

stop_then_status() {
  local user="$1"
  local host="$2"
  local stop_cmd="$3"
  local status_cmd="$4"
  local descriptor="$5"
  echo "  $descriptor: Stopping..."
  run_remote "$user" "$host" "$stop_cmd" >/dev/null 2>&1 || true
  sleep 2
  local result
  result=$(run_remote "$user" "$host" "$status_cmd" 2>/dev/null || echo "DOWN")
  echo "  $descriptor: $result"
}

up_all() {
  echo "COMPOSER UP"
  echo

  echo "[RabbitMQ Service]"
  start_if_needed "$RMQ_SSH_USER" "$RMQ_HOST" "$RMQ_SERVICE_STATUS" "$RMQ_SERVICE_START" "RabbitMQ (rabbitmq-server)"
  echo

  echo "[DB/MySQL Services]"
  start_if_needed "$DB_SSH_USER" "$DB_HOST" "$MYSQL_SERVICE_STATUS" "$MYSQL_SERVICE_START" "MySQL (mysqld)"
  start_if_needed "$DB_SSH_USER" "$DB_HOST" "$DB_WORKER_STATUS" "$DB_WORKER_START" "DB Worker (db_worker.py)"
  echo

  echo "[BE-DB Service]"
  start_if_needed "$BE_DB_SSH_USER" "$BE_DB_HOST" "$BE_DB_STATUS" "$BE_DB_START" "BE-DB Worker (be_db.py)"
  echo

  echo "[BE-FE Service]"
  start_if_needed "$BE_FE_SSH_USER" "$BE_FE_HOST" "$BE_FE_STATUS" "$BE_FE_START" "BE-FE Worker (worker.py)"
  echo

  echo "[Frontend Service]"
  start_if_needed "$FE_SSH_USER" "$FE_HOST" "$FE_STATUS" "$FE_START" "Frontend App (app.py)"
  echo

  echo "UP COMPLETE"
}

down_all() {
  echo "COMPOSER DOWN"
  echo

  echo "[Frontend Service]"
  stop_then_status "$FE_SSH_USER" "$FE_HOST" "$FE_STOP" "$FE_STATUS" "Frontend App (app.py)"
  echo

  echo "[BE-FE Service]"
  stop_then_status "$BE_FE_SSH_USER" "$BE_FE_HOST" "$BE_FE_STOP" "$BE_FE_STATUS" "BE-FE Worker (worker.py)"
  echo

  echo "[BE-DB Service]"
  stop_then_status "$BE_DB_SSH_USER" "$BE_DB_HOST" "$BE_DB_STOP" "$BE_DB_STATUS" "BE-DB Worker (be_db.py)"
  echo

  echo "[DB/MySQL Services]"
  stop_then_status "$DB_SSH_USER" "$DB_HOST" "$DB_WORKER_STOP" "$DB_WORKER_STATUS" "DB Worker (db_worker.py)"
  stop_then_status "$DB_SSH_USER" "$DB_HOST" "$MYSQL_SERVICE_STOP" "$MYSQL_SERVICE_STATUS" "MySQL (mysqld)"
  echo

  echo "[RabbitMQ Service]"
  stop_then_status "$RMQ_SSH_USER" "$RMQ_HOST" "$RMQ_SERVICE_STOP" "$RMQ_SERVICE_STATUS" "RabbitMQ (rabbitmq-server)"
  echo

  echo "DOWN COMPLETE"
}

status_all() {
  echo "COMPOSER STATUS"
  echo

  echo "[RabbitMQ Service]"
  show_status "$RMQ_SSH_USER" "$RMQ_HOST" "$RMQ_SERVICE_STATUS" "RabbitMQ (rabbitmq-server)"
  echo

  echo "[DB/MySQL Services]"
  show_status "$DB_SSH_USER" "$DB_HOST" "$MYSQL_SERVICE_STATUS" "MySQL (mysqld)"
  show_status "$DB_SSH_USER" "$DB_HOST" "$DB_WORKER_STATUS" "DB Worker (db_worker.py)"
  echo

  echo "[BE-DB Service]"
  show_status "$BE_DB_SSH_USER" "$BE_DB_HOST" "$BE_DB_STATUS" "BE-DB Worker (be_db.py)"
  echo

  echo "[BE-FE Service]"
  show_status "$BE_FE_SSH_USER" "$BE_FE_HOST" "$BE_FE_STATUS" "BE-FE Worker (worker.py)"
  echo

  echo "[Frontend Service]"
  show_status "$FE_SSH_USER" "$FE_HOST" "$FE_STATUS" "Frontend App (app.py)"
  echo

  echo "STATUS COMPLETE"
}

logs_all() {
  echo "COMPOSER LOGS"
  echo "Ctrl+C to stop"
  echo

  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

  trap 'kill $(jobs -p) 2>/dev/null; echo; echo "LOGS STOPPED"; exit 0' INT

  run_remote "$FE_SSH_USER"    "$FE_HOST"    "truncate -s 0 $FE_LOG"       2>/dev/null || true
  run_remote "$BE_FE_SSH_USER" "$BE_FE_HOST" "truncate -s 0 $BE_FE_LOG"    2>/dev/null || true
  run_remote "$DB_SSH_USER"    "$DB_HOST"    "truncate -s 0 $DB_WORKER_LOG" 2>/dev/null || true
  run_remote "$BE_DB_SSH_USER" "$BE_DB_HOST" "truncate -s 0 $BE_DB_LOG"     2>/dev/null || true

  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 -i "$SSH_KEY" \
    "$FE_SSH_USER@$FE_HOST" "tail -n 30 -f $FE_LOG" 2>/dev/null \
    | awk '{print "FE| " $0}' &

  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 -i "$SSH_KEY" \
    "$BE_FE_SSH_USER@$BE_FE_HOST" "tail -n 30 -f $BE_FE_LOG" 2>/dev/null \
    | awk '{print "BE-FE| " $0}' &

  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 -i "$SSH_KEY" \
    "$DB_SSH_USER@$DB_HOST" "tail -n 30 -f $DB_WORKER_LOG" 2>/dev/null \
    | awk '{print "DB| " $0}' &

  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 -i "$SSH_KEY" \
    "$BE_DB_SSH_USER@$BE_DB_HOST" "tail -n 30 -f $BE_DB_LOG" 2>/dev/null \
    | awk '{print "BE-DB| " $0}' &

  if [ -f "$SCRIPT_DIR/composer_logs.py" ]; then
    python3 "$SCRIPT_DIR/composer_logs.py"
  else
    wait
  fi
}

case "${1:-}" in
  up)     up_all ;;
  down)   down_all ;;
  status) status_all ;;
  logs)   logs_all ;;
  *)
    echo "Usage: ./composer.sh {up|down|status|logs}"
    exit 1
    ;;
esac