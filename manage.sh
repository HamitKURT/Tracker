#!/bin/bash

# File to store PIDs
PID_FILE="service_pids.txt"

start_services() {
    # Navigate to the script's directory
    cd "$(dirname "$0")"


    source venv/bin/activate
    if [ -z "$VIRTUAL_ENV" ]; then
        echo "❌ Virtual environment is not activated."
        echo "👉 Run: python3 -m venv venv; source venv/bin/activate"
        exit 1
    fi


    
    echo "[Tracker] Bringing up Docker containers (Redis, Elasticsearch, Kibana)..."
    docker compose up -d

    echo "[Tracker] Waiting for Elasticsearch to become ready..."
    until curl -s -u "${ES_USER:-elastic}:${ES_PASSWORD:-changeme}" "http://localhost:9200" | grep -q "cluster_name"; do
      sleep 2
    done

    echo "[Tracker] Initializing internal Kibana system user password..."
    curl -s -X POST -u "${ES_USER:-elastic}:${ES_PASSWORD:-changeme}" "http://localhost:9200/_security/user/kibana_system/_password" -H "Content-Type: application/json" -d '{"password":"'${KIBANA_PASSWORD:-changeme}'"}' > /dev/null

    echo "[Tracker] Installing Python dependencies..."
    pip3 install -r requirements.txt

    echo "[Tracker] Starting Flask log_server on Port 9000..."
    python3 log_server/main.py &
    SERVER_PID=$!

    echo "[Tracker] Starting Elasticsearch log_worker..."
    python3 log_worker/main.py &
    WORKER_PID=$!

    echo "[Tracker] Starting Flask web_app on Port 8081..."
    python3 web_app/app.py &
    WEBAPP_PID=$!


    echo ""
    echo "========================================================"
    echo " 🚀 Tracker system is RUNNING in the background."
    echo " 🌐 Web App URL: http://localhost:8081"
    echo " 📊 Kibana URL:  http://localhost:5601"
    echo " ❌ Press [CTRL+C] to gracefully stop all Python processes."
    echo "========================================================"
    echo ""


    echo "[Tracker] Waiting for Kibana to be ready..."
    until curl -s http://localhost:5601/api/status | grep -q '"overall":{"level":"available"'; do
      echo "Kibana not ready yet... retrying in 3s"
      sleep 3
    done

    echo "[Tracker] Kibana is ready. Executing dashboard deployer..."
    python3 kibana_deployer/main.py &
    DEPLOY_PID=$!


    echo $SERVER_PID > $PID_FILE
    echo $WORKER_PID >> $PID_FILE
    echo $WEBAPP_PID >> $PID_FILE
    echo $DEPLOY_PID >> $PID_FILE

    # Trap SIGINT (Ctrl+C) and SIGTERM to easily clean up the background processes
    trap "echo -e '\n[Tracker] Stopping all Python services...'; kill $SERVER_PID $WORKER_PID $WEBAPP_PID $DEPLOY_PID 2>/dev/null; rm $PID_FILE; exit 0" SIGINT SIGTERM

    # Wait continuously to keep the script running and trap signals
    wait
  
    echo "[Tracker] All services started. PIDs stored in $PID_FILE"
}


stop_services() {
    if [[ ! -f $PID_FILE ]]; then
        echo "No PID file found. Nothing to stop."

        # 1. Kill everything and delete the persistent storage (volumes)
        docker-compose down -v
        # 2. (Optional but recommended) Prune orphaned networks
        docker network prune -f
        echo "[Tracker] All containers and orphaned networks stopped."

        exit 1
    fi

    echo "[Tracker] Stopping services..."
    while IFS= read -r pid; do
        if ps -p $pid > /dev/null 2>&1; then
            echo "Stopping process PID $pid"
            kill $pid
            sleep 1
            # If still running, force kill
            if ps -p $pid > /dev/null 2>&1; then
                echo "Force killing PID $pid"
                kill -9 $pid
            fi
        fi
    done < "$PID_FILE"

    rm -f "$PID_FILE"
    echo "[Tracker] All services stopped."

    # 1. Kill everything and delete the persistent storage (volumes)
    docker-compose down -v

    # 2. (Optional but recommended) Prune orphaned networks
    docker network prune -f

    echo "[Tracker] All Docker containers and orphaned networks stopped."
}


case "$1" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        stop_services
        start_services
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}"
        exit 1
        ;;
esac

