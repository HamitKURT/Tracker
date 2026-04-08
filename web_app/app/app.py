import os
import logging
import time as _time
from flask import Flask, render_template

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html",
        api_endpoint=os.getenv("LOGSERVER_EXTERNAL_URL", "http://localhost:8084"),
        api_endpoint_internal=os.getenv("LOGSERVER_INTERNAL_URL", "http://log-server:8084"),
        debug_mode=os.getenv("DEBUG", "false")
    )

@app.route("/api/slow-response")
def slow_response():
    _time.sleep(6)
    return "OK", 200

@app.after_request
def add_security_headers(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-eval' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src *; "
        "font-src 'none'; "
        "frame-src 'none'"
    )
    return response

@app.route("/dashboard")
def dashboard():
    return render_template("index.html",
        api_endpoint=os.getenv("LOGSERVER_EXTERNAL_URL", "http://localhost:8084"),
        api_endpoint_internal=os.getenv("LOGSERVER_INTERNAL_URL", "http://log-server:8084"),
        debug_mode=os.getenv("DEBUG", "false")
    )

if __name__ == "__main__":
    WEBAPP_PORT = int(os.getenv("PORT", 8081))
    WEBAPP_HOST = os.getenv("HOST", "0.0.0.0")
    logger.info(f"Starting WebApp on {WEBAPP_HOST}:{WEBAPP_PORT}")
    app.run(host=WEBAPP_HOST, port=WEBAPP_PORT, debug=False)
