import os
import json
import logging
import time
from datetime import datetime, timezone
import redis
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

logging.basicConfig(level=logging.INFO, format='%(asctime)s - WORKER - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REDIS_HOST     = os.getenv("REDIS_HOST", "redis")
REDIS_PORT     = int(os.getenv("REDIS_PORT", 6379))
ELASTIC_URL    = os.getenv("ELASTIC_URL", "http://elasticsearch:9200")
ELASTIC_USERNAME = os.getenv("ELASTIC_USERNAME", os.getenv("ELASTIC_USER", "elastic"))
ELASTIC_PASSWORD = os.getenv("ELASTIC_PASSWORD", "changeme")
INDEX          = os.getenv("ELASTIC_INDEX", "selenium-events")
REDIS_QUEUE_KEY = os.getenv("REDIS_QUEUE_KEY", "selenium_logs")
BATCH_SIZE     = int(os.getenv("BATCH_SIZE", 50))
MAX_WAIT_TIME  = float(os.getenv("MAX_WAIT_TIME", 2.0))


def now_utc() -> str:
    """
    Returns current UTC time in Elasticsearch-compatible ISO 8601 format.
    Uses 'Z' suffix instead of '+00:00' — both are valid ISO 8601 but
    Elasticsearch's strict_date_optional_time parser handles 'Z' reliably
    across all versions. '+00:00' can cause silent parse failures in ES 8+/9+
    which makes Kibana's time filter unable to locate the documents.
    Example output: 2026-03-26T08:45:12.345Z
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def normalise_timestamp(value) -> str | None:
    """
    Normalise an incoming timestamp string to the same Z-suffix format.
    Accepts ISO 8601 strings with any UTC offset or Z suffix.
    Returns None if the value cannot be parsed — field will be dropped
    rather than causing the whole document to fail indexing.
    """
    if not value or not isinstance(value, str):
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f+00:00",
        "%Y-%m-%dT%H:%M:%S+00:00",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            dt = datetime.strptime(value.replace("+00:00", "").rstrip("Z"), fmt.rstrip("Z").replace("+00:00", ""))
            return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        except ValueError:
            continue
    logger.warning(f"Could not parse timestamp value: {value!r} — dropping field")
    return None


def connect_services():
    while True:
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            r.ping()
            logger.info("Connected to Redis successfully.")

            es = Elasticsearch(
                ELASTIC_URL,
                basic_auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
                verify_certs=False,
            )
            if not es.ping():
                raise ConnectionError(f"Elasticsearch ping failed at {ELASTIC_URL}")
            logger.info(f"Connected to Elasticsearch at {ELASTIC_URL}")
            return r, es
        except Exception as e:
            logger.error(f"Waiting for services to become available: {e}")
            time.sleep(5)


def setup_index(es):
    mappings = {
        "properties": {
            # Base fields
            "@timestamp":                {"type": "date"},
            "client_time":               {"type": "date"},
            "time":                      {"type": "date"},
            "session_id":                {"type": "keyword"},
            "type":                      {"type": "keyword"},
            "event":                     {"type": "keyword"},
            "url":                       {"type": "keyword"},
            "user_agent":                {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "is_webdriver":              {"type": "boolean"},
            "language":                   {"type": "keyword"},
            "screen_resolution":         {"type": "keyword"},

            # Element info
            "tag":                       {"type": "keyword"},
            "id":                        {"type": "keyword"},
            "class":                     {"type": "keyword"},
            "name":                      {"type": "keyword"},
            "xpath":                     {"type": "keyword"},
            "selector":                  {"type": "keyword"},
            "target_xpath":              {"type": "keyword"},
            "anchor_xpath":              {"type": "keyword"},
            "focus_xpath":               {"type": "keyword"},

            # DOM Query
            "method":                    {"type": "keyword"},
            "found":                     {"type": "boolean"},
            "result_count":              {"type": "integer"},
            "result":                    {"type": "boolean"},

            # Element Inspection
            "width":                     {"type": "float"},
            "height":                    {"type": "float"},
            "pseudo":                    {"type": "keyword"},
            "value":                     {"type": "text"},

            # Data Extraction
            "attribute":                 {"type": "keyword"},

            # Interaction
            "is_trusted":                {"type": "boolean"},
            "page_x":                    {"type": "integer"},
            "page_y":                    {"type": "integer"},
            "value_length":              {"type": "integer"},

            # Timing Alert
            "suspicious":                {"type": "boolean"},
            "interval_ms":                {"type": "integer"},

            # JS Error
            "message":                   {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "source":                    {"type": "keyword"},
            "lineno":                    {"type": "integer"},
            "colno":                     {"type": "integer"},
            "stack":                     {"type": "text"},
            "level":                     {"type": "keyword"},
            "args_count":                {"type": "integer"},

            # Visibility
            "state":                     {"type": "keyword"},

            # Network request
            "request_url":               {"type": "keyword"},
            "request_method":            {"type": "keyword"},
            "status_code":               {"type": "integer"},
            "duration_ms":               {"type": "integer"},
            "request_type":              {"type": "keyword"},
            "success":                   {"type": "boolean"},

            # Performance
            "dom_content_loaded_ms":     {"type": "integer"},
            "load_complete_ms":          {"type": "integer"},
            "first_paint_ms":            {"type": "integer"},
            "first_contentful_paint_ms": {"type": "integer"},
            "dom_interactive_ms":        {"type": "integer"},
            "redirect_count":            {"type": "integer"},
            "transfer_size_bytes":        {"type": "long"},
            "resource_count":             {"type": "integer"},

            # Form submit
            "form_id":                   {"type": "keyword"},
            "form_action":               {"type": "keyword"},
            "form_method":               {"type": "keyword"},
            "field_count":               {"type": "integer"},

            # Clipboard
            "action":                    {"type": "keyword"},
            "target_tag":                {"type": "keyword"},
            "target_id":                 {"type": "keyword"},
            "clipboard_length":          {"type": "integer"},

            # Context menu & mouse
            "x":                         {"type": "integer"},
            "y":                         {"type": "integer"},

            # Resize
            "previous_width":            {"type": "integer"},
            "previous_height":           {"type": "integer"},

            # Connection
            "effective_type":           {"type": "keyword"},
            "downlink":                  {"type": "float"},
            "status":                    {"type": "keyword"},

            # Page unload
            "time_on_page_ms":           {"type": "integer"},
            "event_count":               {"type": "integer"},

            # Navigation
            "navigation_type":           {"type": "keyword"},
            "referrer":                  {"type": "keyword"},
            "from_url":                  {"type": "keyword"},

            # Automation Detection
            "signals":                   {"type": "object", "enabled": True},
            "severity":                  {"type": "keyword"},

            # Automation Alerts
            "alert":                     {"type": "keyword"},

            # MutationObserver
            "mutation_count":            {"type": "integer"},
            "subtree":                   {"type": "boolean"},

            # Selection
            "selected_text":             {"type": "text"},

            # Value Manipulation
            "input_type":                {"type": "keyword"},
            "checked":                   {"type": "boolean"},
            "value_preview":             {"type": "text"},
            "is_suspicious_stack":       {"type": "boolean"},
        }
    }
    try:
        if not es.indices.exists(index=INDEX):
            logger.info(f"Creating index '{INDEX}'.")
            es.indices.create(index=INDEX, mappings=mappings)
            logger.info("Index created successfully.")
        else:
            logger.info(f"Index '{INDEX}' already exists. Updating mappings.")
            es.indices.put_mapping(index=INDEX, properties=mappings["properties"])
    except Exception as e:
        logger.warning(f"Error checking/creating index: {e}")


def process_logs():
    r, es = connect_services()
    setup_index(es)

    logger.info(f"Starting log consumption from queue '{REDIS_QUEUE_KEY}'")

    while True:
        batch      = []
        start_time = time.time()

        while len(batch) < BATCH_SIZE and (time.time() - start_time) < MAX_WAIT_TIME:
            item = r.brpop(REDIS_QUEUE_KEY, timeout=1)
            if item:
                _, data = item
                try:
                    event = json.loads(data)
                    if not isinstance(event, dict):
                        event = {"raw_payload": event}
                except json.JSONDecodeError:
                    event = {"raw_data": data}

                # Always overwrite @timestamp with a correctly formatted UTC value.
                # isoformat() produces "+00:00" suffix which ES strict parser mishandles.
                event["@timestamp"] = now_utc()

                # Normalise client_time if present so Kibana can use it as a date field.
                if "client_time" in event:
                    normalised = normalise_timestamp(event["client_time"])
                    if normalised:
                        event["client_time"] = normalised
                    else:
                        del event["client_time"]

                batch.append({"_index": INDEX, "_source": event})

        if batch:
            try:
                success, _ = bulk(es, batch)
                logger.info(f"Successfully indexed {success} documents.")
            except Exception as e:
                logger.error(f"Elasticsearch bulk index failed: {e}")


if __name__ == "__main__":
    process_logs()