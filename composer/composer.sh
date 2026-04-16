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

  # RMQ
  echo "[RabbitMQ Service]"
  start_if_needed "$RMQ_SSH_USER" "$RMQ_HOST" "$RMQ_SERVICE_STATUS" "$RMQ_SERVICE_START" "RabbitMQ (rabbitmq-server)"
  echo

  echo "[RabbitMQ Service - Node 2]"
  start_if_needed "$RMQ2_SSH_USER" "$RMQ2_HOST" "$RMQ_SERVICE_STATUS" "$RMQ_SERVICE_START" "RabbitMQ2 (rabbitmq-server)"
  echo

  echo "[RabbitMQ Service - Node 3]"
  start_if_needed "$RMQ3_SSH_USER" "$RMQ3_HOST" "$RMQ_SERVICE_STATUS" "$RMQ_SERVICE_START" "RabbitMQ3 (rabbitmq-server)"
  echo

  # DB
  echo "[DB/MySQL Services - Node 1]"
  start_if_needed "$DB_SSH_USER" "$DB_HOST" "$MYSQL_SERVICE_STATUS" "$MYSQL_SERVICE_START" "MySQL DB1 (mysqld)"
  echo

  echo "[DB/MySQL Services - Node 2]"
  start_if_needed "$DB2_SSH_USER" "$DB2_HOST" "$MYSQL_SERVICE_STATUS" "$MYSQL_SERVICE_START" "MySQL DB2 (mysqld)"
  echo

  echo "[DB/MySQL Services - Node 3]"
  start_if_needed "$DB3_SSH_USER" "$DB3_HOST" "$MYSQL_SERVICE_STATUS" "$MYSQL_SERVICE_START" "MySQL DB3 (mysqld)"
  echo

echo "[DB Cluster Bootstrap]"
CLUSTER_COUNT=0
for TRY_HOST in "$DB_HOST" "$DB2_HOST" "$DB3_HOST"; do
  CLUSTER_COUNT=$(run_remote "$DB_SSH_USER" "$TRY_HOST" "mysql -u root -proot123 -h 127.0.0.1 -e \"SELECT COUNT(*) FROM performance_schema.replication_group_members WHERE MEMBER_STATE='ONLINE';\" 2>/dev/null | grep -v COUNT | tr -d ' '" 2>/dev/null || echo "0")
  if [ "$CLUSTER_COUNT" -ge 1 ] 2>/dev/null; then
    break
  fi
done

if [ "$CLUSTER_COUNT" -ge 1 ] 2>/dev/null; then
  echo "  Cluster already formed ($CLUSTER_COUNT nodes ONLINE) — skipping bootstrap"
else
  echo "  Bootstrapping cluster from DB1..."
  run_remote "$DB_SSH_USER" "$DB_HOST" "mysql -u root -proot123 -h 127.0.0.1 -e \"STOP GROUP_REPLICATION; RESET REPLICA ALL; SET GLOBAL group_replication_bootstrap_group=ON; START GROUP_REPLICATION USER='replication_user', PASSWORD='replicapass123'; SET GLOBAL group_replication_bootstrap_group=OFF;\"" >/dev/null 2>&1 || true
  sleep 10
  echo "  Joining DB2..."
  run_remote "$DB2_SSH_USER" "$DB2_HOST" "mysql -u root -proot123 -h 127.0.0.1 -e \"STOP GROUP_REPLICATION; RESET REPLICA ALL; RESET MASTER; START GROUP_REPLICATION USER='replication_user', PASSWORD='replicapass123';\"" >/dev/null 2>&1 || true
  sleep 10
  echo "  Joining DB3..."
  run_remote "$DB3_SSH_USER" "$DB3_HOST" "mysql -u root -proot123 -h 127.0.0.1 -e \"STOP GROUP_REPLICATION; RESET REPLICA ALL; RESET MASTER; START GROUP_REPLICATION USER='replication_user', PASSWORD='replicapass123';\"" >/dev/null 2>&1 || true
  sleep 5
fi
echo

echo "[MySQL Router - Node 1]"
ROUTER_UP=$(run_remote "$DB_SSH_USER" "$DB_HOST" "$ROUTER_STATUS" 2>/dev/null || echo "DOWN")
if [ "$ROUTER_UP" = "UP" ]; then
  echo "  MySQL Router DB1: Already UP"
else
  echo "  MySQL Router DB1: Starting..."
  run_remote "$DB_SSH_USER" "$DB_HOST" "$ROUTER_BOOTSTRAP" >/dev/null 2>&1 || true
  run_remote "$DB_SSH_USER" "$DB_HOST" "$ROUTER_START" >/dev/null 2>&1 || true
  sleep 5
  show_status "$DB_SSH_USER" "$DB_HOST" "$ROUTER_STATUS" "MySQL Router DB1"
fi
echo

echo "[MySQL Router - Node 2]"
ROUTER_UP=$(run_remote "$DB2_SSH_USER" "$DB2_HOST" "$ROUTER_STATUS" 2>/dev/null || echo "DOWN")
if [ "$ROUTER_UP" = "UP" ]; then
  echo "  MySQL Router DB2: Already UP"
else
  echo "  MySQL Router DB2: Starting..."
  run_remote "$DB2_SSH_USER" "$DB2_HOST" "$ROUTER2_BOOTSTRAP" >/dev/null 2>&1 || true
  run_remote "$DB2_SSH_USER" "$DB2_HOST" "$ROUTER_START" >/dev/null 2>&1 || true
  sleep 5
  show_status "$DB2_SSH_USER" "$DB2_HOST" "$ROUTER_STATUS" "MySQL Router DB2"
fi
echo

echo "[MySQL Router - Node 3]"
ROUTER_UP=$(run_remote "$DB3_SSH_USER" "$DB3_HOST" "$ROUTER_STATUS" 2>/dev/null || echo "DOWN")
if [ "$ROUTER_UP" = "UP" ]; then
  echo "  MySQL Router DB3: Already UP"
else
  echo "  MySQL Router DB3: Starting..."
  run_remote "$DB3_SSH_USER" "$DB3_HOST" "$ROUTER3_BOOTSTRAP" >/dev/null 2>&1 || true
  run_remote "$DB3_SSH_USER" "$DB3_HOST" "$ROUTER_START" >/dev/null 2>&1 || true
  sleep 5
  show_status "$DB3_SSH_USER" "$DB3_HOST" "$ROUTER_STATUS" "MySQL Router DB3"
fi
echo


  echo "[DB Worker - Node 1]"
  start_if_needed "$DB_SSH_USER" "$DB_HOST" "$DB_WORKER_STATUS" "$DB_WORKER_START" "DB Worker DB1 (db_worker.py)"
  echo

  echo "[DB Worker - Node 2]"
  start_if_needed "$DB2_SSH_USER" "$DB2_HOST" "$DB_WORKER_STATUS" "$DB2_WORKER_START" "DB Worker DB2 (db_worker.py)"
  echo

  echo "[DB Worker - Node 3]"
  start_if_needed "$DB3_SSH_USER" "$DB3_HOST" "$DB_WORKER_STATUS" "$DB3_WORKER_START" "DB Worker DB3 (db_worker.py)"
  echo

  # BE-DB
  echo "[BE-DB Service]"
  start_if_needed "$BE_DB_SSH_USER" "$BE_DB_HOST" "$BE_DB_STATUS" "$BE_DB_START" "BE-DB Worker (be_db.py)"
  echo

  echo "[BE-DB Service - Node 2]"
  start_if_needed "$BE_DB2_SSH_USER" "$BE_DB2_HOST" "$BE_DB_STATUS" "$BE_DB_START" "BE-DB2 Worker (be_db.py)"
  echo

  # BE-FE
  echo "[BE-FE Service]"
  start_if_needed "$BE_FE_SSH_USER" "$BE_FE_HOST" "$BE_FE_STATUS" "$BE_FE_START" "BE-FE Worker (worker.py)"
  echo

  echo "[BE-FE Service - Node 2]"
  start_if_needed "$BE_FE2_SSH_USER" "$BE_FE2_HOST" "$BE_FE_STATUS" "$BE_FE_START" "BE-FE2 Worker (worker.py)"
  echo

  # FE
  echo "[Frontend Service]"
  start_if_needed "$FE_SSH_USER" "$FE_HOST" "$FE_STATUS" "$FE_START" "Frontend App FE1 (app.py)"
  echo

  echo "[Frontend Service - Node 2]"
  start_if_needed "$FE2_SSH_USER" "$FE2_HOST" "$FE_STATUS" "$FE_START" "Frontend App FE2 (app.py)"
  echo

  echo "[Nginx Load Balancer]"
  start_if_needed "$FE_SSH_USER" "$FE_HOST" "$NGINX_STATUS" "$NGINX_START" "Nginx (load balancer)"
  echo

  echo "UP COMPLETE"
}

down_all() {
  echo "COMPOSER DOWN"
  echo

  # FE
  echo "[Nginx Load Balancer]"
  stop_then_status "$FE_SSH_USER" "$FE_HOST" "$NGINX_STOP" "$NGINX_STATUS" "Nginx (load balancer)"
  echo

  echo "[Frontend Service - Node 2]"
  stop_then_status "$FE2_SSH_USER" "$FE2_HOST" "$FE_STOP" "$FE_STATUS" "Frontend App FE2 (app.py)"
  echo

  echo "[Frontend Service]"
  stop_then_status "$FE_SSH_USER" "$FE_HOST" "$FE_STOP" "$FE_STATUS" "Frontend App FE1 (app.py)"
  echo

  # BE-FE
  echo "[BE-FE Service - Node 2]"
  stop_then_status "$BE_FE2_SSH_USER" "$BE_FE2_HOST" "$BE_FE_STOP" "$BE_FE_STATUS" "BE-FE2 Worker (worker.py)"
  echo

  echo "[BE-FE Service]"
  stop_then_status "$BE_FE_SSH_USER" "$BE_FE_HOST" "$BE_FE_STOP" "$BE_FE_STATUS" "BE-FE Worker (worker.py)"
  echo

  # BE-DB
  echo "[BE-DB Service - Node 2]"
  stop_then_status "$BE_DB2_SSH_USER" "$BE_DB2_HOST" "$BE_DB_STOP" "$BE_DB_STATUS" "BE-DB2 Worker (be_db.py)"
  echo

  echo "[BE-DB Service]"
  stop_then_status "$BE_DB_SSH_USER" "$BE_DB_HOST" "$BE_DB_STOP" "$BE_DB_STATUS" "BE-DB Worker (be_db.py)"
  echo

  # DB
  echo "[DB Worker - Node 3]"
  stop_then_status "$DB3_SSH_USER" "$DB3_HOST" "$DB_WORKER_STOP" "$DB_WORKER_STATUS" "DB Worker DB3 (db_worker.py)"
  echo

  echo "[DB Worker - Node 2]"
  stop_then_status "$DB2_SSH_USER" "$DB2_HOST" "$DB_WORKER_STOP" "$DB_WORKER_STATUS" "DB Worker DB2 (db_worker.py)"
  echo

  echo "[DB Worker - Node 1]"
  stop_then_status "$DB_SSH_USER" "$DB_HOST" "$DB_WORKER_STOP" "$DB_WORKER_STATUS" "DB Worker DB1 (db_worker.py)"
  echo

  echo "[MySQL Router - Node 3]"
  stop_then_status "$DB3_SSH_USER" "$DB3_HOST" "$ROUTER_STOP" "$ROUTER_STATUS" "MySQL Router DB3"
  echo

  echo "[MySQL Router - Node 2]"
  stop_then_status "$DB2_SSH_USER" "$DB2_HOST" "$ROUTER_STOP" "$ROUTER_STATUS" "MySQL Router DB2"
  echo

  echo "[MySQL Router - Node 1]"
  stop_then_status "$DB_SSH_USER" "$DB_HOST" "$ROUTER_STOP" "$ROUTER_STATUS" "MySQL Router DB1"
  echo

  echo "[DB/MySQL Services - Node 3]"
  stop_then_status "$DB3_SSH_USER" "$DB3_HOST" "$MYSQL_SERVICE_STOP" "$MYSQL_SERVICE_STATUS" "MySQL DB3 (mysqld)"
  sleep 10
  echo

  echo "[DB/MySQL Services - Node 2]"
  stop_then_status "$DB2_SSH_USER" "$DB2_HOST" "$MYSQL_SERVICE_STOP" "$MYSQL_SERVICE_STATUS" "MySQL DB2 (mysqld)"
  sleep 10
  echo

  echo "[DB/MySQL Services - Node 1]"
  stop_then_status "$DB_SSH_USER" "$DB_HOST" "$MYSQL_SERVICE_STOP" "$MYSQL_SERVICE_STATUS" "MySQL DB1 (mysqld)"
  echo

  # RMQ
  echo "[RabbitMQ Service - Node 3]"
  stop_then_status "$RMQ3_SSH_USER" "$RMQ3_HOST" "$RMQ_SERVICE_STOP" "$RMQ_SERVICE_STATUS" "RabbitMQ3 (rabbitmq-server)"
  echo

  echo "[RabbitMQ Service - Node 2]"
  stop_then_status "$RMQ2_SSH_USER" "$RMQ2_HOST" "$RMQ_SERVICE_STOP" "$RMQ_SERVICE_STATUS" "RabbitMQ2 (rabbitmq-server)"
  echo

  echo "[RabbitMQ Service]"
  stop_then_status "$RMQ_SSH_USER" "$RMQ_HOST" "$RMQ_SERVICE_STOP" "$RMQ_SERVICE_STATUS" "RabbitMQ (rabbitmq-server)"
  echo

  echo "DOWN COMPLETE"
}

status_all() {
  echo "COMPOSER STATUS"
  echo

  # RMQ
  echo "[RabbitMQ Service]"
  show_status "$RMQ_SSH_USER" "$RMQ_HOST" "$RMQ_SERVICE_STATUS" "RabbitMQ (rabbitmq-server)"
  echo

  echo "[RabbitMQ Service - Node 2]"
  show_status "$RMQ2_SSH_USER" "$RMQ2_HOST" "$RMQ_SERVICE_STATUS" "RabbitMQ2 (rabbitmq-server)"
  echo

  echo "[RabbitMQ Service - Node 3]"
  show_status "$RMQ3_SSH_USER" "$RMQ3_HOST" "$RMQ_SERVICE_STATUS" "RabbitMQ3 (rabbitmq-server)"
  echo

  # DB
  echo "[DB/MySQL Services - Node 1]"
  show_status "$DB_SSH_USER" "$DB_HOST" "$MYSQL_SERVICE_STATUS" "MySQL DB1 (mysqld)"
  show_status "$DB_SSH_USER" "$DB_HOST" "$ROUTER_STATUS" "MySQL Router DB1"
  show_status "$DB_SSH_USER" "$DB_HOST" "$DB_WORKER_STATUS" "DB Worker DB1 (db_worker.py)"
  ROLE1=$(run_remote "$DB_SSH_USER" "$DB_HOST" "mysql -u root -proot123 -h 127.0.0.1 -e \"SELECT MEMBER_ROLE FROM performance_schema.replication_group_members WHERE MEMBER_HOST='100.78.226.13';\" 2>/dev/null | grep -v MEMBER_ROLE | tr -d ' '" 2>/dev/null || echo "UNKNOWN")
  echo "  Cluster Role: $ROLE1"
  echo

  echo "[DB/MySQL Services - Node 2]"
  show_status "$DB2_SSH_USER" "$DB2_HOST" "$MYSQL_SERVICE_STATUS" "MySQL DB2 (mysqld)"
  show_status "$DB2_SSH_USER" "$DB2_HOST" "$ROUTER_STATUS" "MySQL Router DB2"
  show_status "$DB2_SSH_USER" "$DB2_HOST" "$DB_WORKER_STATUS" "DB Worker DB2 (db_worker.py)"
  ROLE2=$(run_remote "$DB2_SSH_USER" "$DB2_HOST" "mysql -u root -proot123 -h 127.0.0.1 -e \"SELECT MEMBER_ROLE FROM performance_schema.replication_group_members WHERE MEMBER_HOST='100.64.56.116';\" 2>/dev/null | grep -v MEMBER_ROLE | tr -d ' '" 2>/dev/null || echo "UNKNOWN")
  echo "  Cluster Role: $ROLE2"
  echo

  echo "[DB/MySQL Services - Node 3]"
  show_status "$DB3_SSH_USER" "$DB3_HOST" "$MYSQL_SERVICE_STATUS" "MySQL DB3 (mysqld)"
  show_status "$DB3_SSH_USER" "$DB3_HOST" "$ROUTER_STATUS" "MySQL Router DB3"
  show_status "$DB3_SSH_USER" "$DB3_HOST" "$DB_WORKER_STATUS" "DB Worker DB3 (db_worker.py)"
  ROLE3=$(run_remote "$DB3_SSH_USER" "$DB3_HOST" "mysql -u root -proot123 -h 127.0.0.1 -e \"SELECT MEMBER_ROLE FROM performance_schema.replication_group_members WHERE MEMBER_HOST='100.124.122.18';\" 2>/dev/null | grep -v MEMBER_ROLE | tr -d ' '" 2>/dev/null || echo "UNKNOWN")
  echo "  Cluster Role: $ROLE3"
  echo

  # BE-DB
  echo "[BE-DB Service]"
  show_status "$BE_DB_SSH_USER" "$BE_DB_HOST" "$BE_DB_STATUS" "BE-DB Worker (be_db.py)"
  echo

  echo "[BE-DB Service - Node 2]"
  show_status "$BE_DB2_SSH_USER" "$BE_DB2_HOST" "$BE_DB_STATUS" "BE-DB2 Worker (be_db.py)"
  echo

  # BE-FE
  echo "[BE-FE Service]"
  show_status "$BE_FE_SSH_USER" "$BE_FE_HOST" "$BE_FE_STATUS" "BE-FE Worker (worker.py)"
  echo

  echo "[BE-FE Service - Node 2]"
  show_status "$BE_FE2_SSH_USER" "$BE_FE2_HOST" "$BE_FE_STATUS" "BE-FE2 Worker (worker.py)"
  echo

  # FE
  echo "[Frontend Service]"
  show_status "$FE_SSH_USER" "$FE_HOST" "$FE_STATUS" "Frontend App FE1 (app.py)"
  echo

  echo "[Frontend Service - Node 2]"
  show_status "$FE2_SSH_USER" "$FE2_HOST" "$FE_STATUS" "Frontend App FE2 (app.py)"
  echo

  echo "[Nginx Load Balancer]"
  show_status "$FE_SSH_USER" "$FE_HOST" "$NGINX_STATUS" "Nginx (load balancer)"
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