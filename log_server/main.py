import os
import json
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
import redis

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Allow CORS for all origins, supporting headers and credentials if necessary
CORS(app, supports_credentials=True)

# Use Environment variable for Redis to allow Dockerization later
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

try:
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    r.ping()
    logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logger.error(f"Failed to connect to Redis at {REDIS_HOST}:{REDIS_PORT}: {e}")

@app.route("/selenium-log", methods=["POST", "OPTIONS"])
def log():
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
            # Not strict JSON, but we will log it raw
            data = {"raw_payload": raw_data}
            
    try:
        # Enqueue the log event
        r.lpush("selenium_logs", json.dumps(data))
        return jsonify({"status": "queued"}), 200
    except redis.RedisError as re:
        logger.error(f"Redis error during lpush: {re}")
        return jsonify({"error": "Queue error"}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"error": "Server error"}), 500

@app.route("/health", methods=["GET"])
def health_check():
    try:
        r.ping()
        return jsonify({"status": "healthy", "redis": "connected"}), 200
    except redis.RedisError:
        return jsonify({"status": "unhealthy", "redis": "disconnected"}), 503

if __name__ == "__main__":
    SERVER_PORT = int(os.getenv("PORT", 9000))
    # Allow host environment variable substitution
    SERVER_HOST = os.getenv("HOST", "0.0.0.0")
    logger.info(f"Starting LogServer on {SERVER_HOST}:{SERVER_PORT}")
    app.run(port=SERVER_PORT, host=SERVER_HOST, debug=False)
