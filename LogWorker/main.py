import redis
import json
from elasticsearch import Elasticsearch
from datetime import datetime, timezone

r = redis.Redis(host="localhost", port=6379, decode_responses=True)
es = Elasticsearch("http://localhost:9200")  # ES host
INDEX = "selenium-events"

while True:
    _, data = r.brpop("selenium_logs")

    # Güvenli JSON parse
    try:
        event = json.loads(data)
        if not isinstance(event, dict):
            # JSON ama dict değilse dict yap
            event = {"raw": event}
    except json.JSONDecodeError:
        # JSON değilse dict olarak kaydet
        event = {"raw": data}

    # timestamp ekle
    event["@timestamp"] = datetime.now(timezone.utc).isoformat()

    # Elasticsearch indexle
    es.index(index=INDEX, document=event)

    print("indexed:", event)
