import os
import json
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
import redis

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, supports_credentials=True)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_QUEUE_KEY = os.getenv("REDIS_QUEUE_KEY", "events_main")

logger.info(f"REDIS_HOST={REDIS_HOST}, REDIS_PORT={REDIS_PORT}, REDIS_QUEUE_KEY={REDIS_QUEUE_KEY}")

try:
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_keepalive=True, socket_connect_timeout=5)
    r.ping()
    logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logger.error(f"Failed to connect to Redis at {REDIS_HOST}:{REDIS_PORT}: {e}")
    r = None


def get_redis_client():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_keepalive=True)


@app.route("/events", methods=["POST", "OPTIONS"])
def handle_event():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    raw_data = None
    data = request.get_json(silent=True)

    if not data:
        raw_data = request.data.decode(errors='ignore')
        if not raw_data:
            logger.warning("Received empty request payload.")
            return jsonify({"error": "Empty payload"}), 400

        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            data = {"raw_payload": raw_data}

    logger.info(f"Received data: type={type(data)}, keys={list(data.keys()) if isinstance(data, dict) else 'N/A'}")

    redis_client = get_redis_client()

    try:
        if isinstance(data, dict) and "events" in data and isinstance(data["events"], list):
            logger.info(f"Processing {len(data['events'])} events from batch")
            for item in data["events"]:
                serialized = json.dumps(item) if isinstance(item, dict) else json.dumps({"raw_payload": item})
                logger.info(f"LPUSH: key={REDIS_QUEUE_KEY}, data_len={len(serialized)}")
                result = redis_client.lpush(REDIS_QUEUE_KEY, serialized)
                logger.info(f"LPUSH result: {result}")
        elif isinstance(data, list):
            logger.info(f"Processing {len(data)} events from list")
            for item in data:
                serialized = json.dumps(item) if isinstance(item, dict) else json.dumps({"raw_payload": item})
                result = redis_client.lpush(REDIS_QUEUE_KEY, serialized)
        else:
            logger.info(f"Processing single event")
            result = redis_client.lpush(REDIS_QUEUE_KEY, json.dumps(data))

        logger.info(f"Successfully queued events to Redis")
        return jsonify({"status": "queued"}), 200
    except redis.RedisError as re:
        logger.error(f"Redis error during lpush: {re}")
        return jsonify({"error": "Queue error"}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"error": "Server error"}), 500


@app.route("/health", methods=["GET"])
def health_check():
    if r is None:
        return jsonify({"status": "unhealthy", "redis": "disconnected"}), 503
    try:
        r.ping()
        return jsonify({"status": "healthy", "redis": "connected"}), 200
    except redis.RedisError:
        return jsonify({"status": "unhealthy", "redis": "disconnected"}), 503


if __name__ == "__main__":
    SERVER_PORT = int(os.getenv("PORT", 8084))
    SERVER_HOST = os.getenv("HOST", "0.0.0.0")
    logger.info(f"Starting LogServer on {SERVER_HOST}:{SERVER_PORT}")
    app.run(port=SERVER_PORT, host=SERVER_HOST, debug=False)
