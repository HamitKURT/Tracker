import os
import json
import logging
import time
from datetime import datetime, timezone
import redis
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - WORKER - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
ES_USER = os.getenv("ES_USER", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "changeme")
INDEX = os.getenv("ES_INDEX", "selenium-events")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 50))
MAX_WAIT_TIME = float(os.getenv("MAX_WAIT_TIME", 2.0)) # Seconds

def connect_services():
    while True:
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            r.ping()
            logger.info("Connected to Redis successfully.")
            
            es = Elasticsearch(ES_HOST, basic_auth=(ES_USER, ES_PASSWORD))
            if not es.ping():
                 raise ConnectionError(f"Elasticsearch ping failed at {ES_HOST}")
            logger.info(f"Connected to Elasticsearch at {ES_HOST}")
            return r, es
        except Exception as e:
            logger.error(f"Waiting for services to become available: {e}")
            time.sleep(5)

def setup_index(es):
    try:
        mappings = {
            "properties": {
                "@timestamp": {"type": "date"},
                "client_time": {"type": "date"},
                "session_id": {"type": "keyword"},
                "type": {"type": "keyword"},
                "event": {"type": "keyword"},
                "url": {"type": "keyword"},
                # Added Metadata
                "user_agent": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "is_webdriver": {"type": "boolean"},
                "language": {"type": "keyword"},
                "screen_resolution": {"type": "keyword"},
                # Added Interaction/Query fields
                "tag": {"type": "keyword"},
                "id": {"type": "keyword"},
                "class": {"type": "keyword"},
                "name": {"type": "keyword"},
                "xpath": {"type": "keyword"},
                "selector": {"type": "keyword"},
                "method": {"type": "keyword"},
                "found": {"type": "boolean"},
                "value_length": {"type": "integer"},
                # Added Bot/Timing alerts
                "suspicious": {"type": "boolean"},
                "interval_ms": {"type": "integer"},
                # Added Error Tracking
                "message": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "source": {"type": "keyword"},
                "lineno": {"type": "integer"},
                "colno": {"type": "integer"},
                # Added Visibility
                "state": {"type": "keyword"}
            }
        }
        
        if not es.indices.exists(index=INDEX):
            logger.info(f"Creating index '{INDEX}'.")
            es.indices.create(index=INDEX, mappings=mappings)
            logger.info(f"Index created successfully.")
        else:
            logger.info(f"Index '{INDEX}' already exists. Updating mappings.")
            es.indices.put_mapping(index=INDEX, properties=mappings["properties"])
            
    except Exception as e:
         logger.warning(f"Error checking/creating index: {e}")

def process_logs():
    r, es = connect_services()
    setup_index(es)
    
    logger.info("Starting log consumption from queue 'selenium_logs'")
    
    while True:
        batch = []
        start_time = time.time()
        
        # Accumulate logs up to BATCH_SIZE or MAX_WAIT_TIME
        while len(batch) < BATCH_SIZE and (time.time() - start_time) < MAX_WAIT_TIME:
            item = r.brpop("selenium_logs", timeout=1)  # wait 1 second
            if item:
                _, data = item
                try:
                    event = json.loads(data)
                    if not isinstance(event, dict):
                        event = {"raw_payload": event}
                except json.JSONDecodeError:
                    event = {"raw_data": data}
                
                # Use server ingestion time
                event["@timestamp"] = datetime.now(timezone.utc).isoformat()
                
                # Prepare Elasticsearch bulk doc wrapper
                action = {
                    "_index": INDEX,
                    "_source": event
                }
                batch.append(action)
                
        # Send batch if any items present
        if batch:
            try:
                success, _ = bulk(es, batch)
                logger.info(f"Successfully indexed {success} documents.")
            except Exception as e:
                logger.error(f"Elasticsearch bulk index failed: {e}")
                
if __name__ == "__main__":
    process_logs()
