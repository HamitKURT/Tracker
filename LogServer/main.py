from flask import Flask, request
from flask_cors import CORS
import redis, json

app = Flask(__name__)
CORS(app)  # <-- bütün originlere izin verir

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

@app.route("/selenium-log", methods=["POST"])
def log():
    data = request.get_json(silent=True)
    if not data:
        data = request.data.decode()
    r.lpush("selenium_logs", json.dumps(data))
    return {"status":"queued"}

if __name__ == "__main__":
    app.run(port=9000, host="0.0.0.0")
