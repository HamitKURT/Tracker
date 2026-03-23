import os
from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html", 
        api_port=os.getenv("API_PORT", "8084"),
        debug_mode=os.getenv("DEBUG", "false")
    )

@app.route("/dashboard")
def dashboard():
    return render_template("index.html",
        api_port=os.getenv("API_PORT", "8084"),
        debug_mode=os.getenv("DEBUG", "false")
    )

if __name__ == "__main__":
    WEBAPP_PORT = int(os.getenv("PORT", 8081))
    WEBAPP_HOST = os.getenv("HOST", "0.0.0.0")
    print(f"Starting WebApp on {WEBAPP_HOST}:{WEBAPP_PORT}")
    app.run(host=WEBAPP_HOST, port=WEBAPP_PORT, debug=False)
