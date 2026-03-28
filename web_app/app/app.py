import os
import logging
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
