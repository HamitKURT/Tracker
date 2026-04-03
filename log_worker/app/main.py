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
REDIS_QUEUE_KEY = os.getenv("REDIS_QUEUE_KEY", "events_main")
BATCH_SIZE     = int(os.getenv("BATCH_SIZE", 50))
MAX_WAIT_TIME  = float(os.getenv("MAX_WAIT_TIME", 2.0))


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def normalise_timestamp(value) -> str | None:
    if not value:
        return None
    # Handle numeric timestamps (milliseconds since epoch from Date.now())
    if isinstance(value, (int, float)):
        try:
            ts = value / 1000.0 if value > 1e12 else float(value)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        except (ValueError, OSError, OverflowError):
            logger.warning(f"Could not parse numeric timestamp: {value!r}")
            return None
    if not isinstance(value, str):
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
    # Note: dynamic=true allows documents with additional/unknown fields to be indexed
    # The explicit mappings below cover all known fields from performance.js
    mappings = {
        "dynamic": "true",
        "properties": {
            # Core fields
            "@timestamp":                {"type": "date"},
            "timestamp":                 {"type": "date"},
            "time":                      {"type": "date"},
            "client_time":               {"type": "date"},

            "sessionId":                 {"type": "keyword"},
            "pageId":                    {"type": "keyword"},
            "correlationId":             {"type": "keyword"},
            "parentId":                  {"type": "keyword"},
            "eventId":                   {"type": "keyword"},
            "uniqueId":                  {"type": "keyword"},

            "type":                      {"type": "keyword"},
            "method":                    {"type": "keyword"},
            "url":                       {"type": "keyword"},
            "from":                      {"type": "keyword"},
            "to":                        {"type": "keyword"},

            "userAgent":                 {"type": "text"},
            "isAutomated":               {"type": "boolean"},
            "isAutomationDetected":      {"type": "boolean"},
            "isTrusted":                 {"type": "boolean"},
            "uptime":                    {"type": "long"},

            # Selector fields
            "selector":                  {"type": "keyword"},
            "selectorPath":              {"type": "keyword"},
            "xpath":                     {"type": "keyword"},
            "expression":                {"type": "keyword"},
            "found":                     {"type": "boolean"},
            "isRepeatedFailure":         {"type": "boolean"},
            "missCount":                 {"type": "integer"},
            "matchCount":                {"type": "integer"},
            "firstAttempt":              {"type": "long"},
            "lastAttempt":               {"type": "long"},
            "timeSinceFirst":            {"type": "long"},
            "likelyIssue":               {"type": "keyword"},

            # Parent path fields
            "parentPath":                {"type": "keyword"},
            "parentTagName":             {"type": "keyword"},
            "parentId":                  {"type": "keyword"},
            "parentClasses":             {"type": "keyword"},

            # Automation context
            "automationContext":         {"type": "boolean"},

            # Selector analysis
            "selectorTagName":           {"type": "keyword"},
            "selectorId":                {"type": "keyword"},
            "selectorClasses":           {"type": "keyword"},
            "selectorAttributes":        {"type": "keyword"},
            "selectorDetails":           {"type": "object"},
            "pseudoClasses":             {"type": "keyword"},
            "combinators":               {"type": "keyword"},
            "xpathAnalysis":             {"type": "object"},
            "containsText":              {"type": "boolean"},
            "containsAttribute":         {"type": "boolean"},
            "containsDescendant":        {"type": "boolean"},
            "containsAxis":              {"type": "boolean"},

            # Error fields
            "message":                   {
                "type": "text",
                "fields": {
                    "keyword": {
                        "type": "keyword",
                        "ignore_above": 2048
                    }
                }
            },
            "filename":                  {"type": "keyword"},
            "source":                    {"type": "keyword"},
            "lineno":                    {"type": "integer"},
            "colno":                     {"type": "integer"},
            "stack":                     {"type": "text"},
            "args":                      {"type": "text"},
            "errorThrown":               {"type": "keyword"},
            "errorCode":                 {"type": "keyword"},
            "reason":                    {"type": "text"},
            "code":                      {"type": "integer"},
            "warning":                   {"type": "keyword"},

            # Network fields
            "requestMethod":             {"type": "keyword"},
            "requestUrl":                {"type": "keyword"},
            "status":                    {"type": "keyword"},
            "statusCode":                {"type": "integer"},
            "duration":                  {"type": "long"},
            "success":                   {"type": "boolean"},
            "pendingRequests":           {"type": "integer"},

            # Performance fields
            "loadTime":                  {"type": "long"},
            "idleMs":                    {"type": "long"},
            "interval":                  {"type": "long"},
            "slow":                      {"type": "boolean"},

            # DOM fields
            "tagName":                   {"type": "keyword"},
            "tag":                       {"type": "keyword"},
            "src":                       {"type": "keyword"},
            "textContent":               {"type": "text"},
            "target":                    {"type": "keyword"},
            "position":                  {"type": "keyword"},
            "nodesAdded":                {"type": "integer"},
            "nodesRemoved":              {"type": "integer"},
            "totalRemoved":              {"type": "integer"},
            "changes":                   {"type": "object"},
            "totalChanges":              {"type": "integer"},
            "removedElements":           {"type": "keyword"},
            "count":                     {"type": "integer"},
            "clickCount":                {"type": "integer"},
            "attribute":                 {"type": "keyword"},

            # Form fields
            "formAction":                {"type": "keyword"},
            "formMethod":                {"type": "keyword"},
            "invalidFields":             {"type": "object"},
            "inputType":                 {"type": "keyword"},
            "checked":                   {"type": "boolean"},
            "value_length":              {"type": "integer"},
            "value_preview":             {"type": "text"},

            # Security/CSP fields
            "blockedURI":                {"type": "keyword"},
            "violatedDirective":         {"type": "keyword"},
            "originalPolicy":            {"type": "keyword"},

            # Framework fields
            "frameworks":                {"type": "object"},
            "componentName":             {"type": "keyword"},
            "componentStack":            {"type": "keyword"},
            "zoneName":                  {"type": "keyword"},
            "info":                      {"type": "keyword"},
            "trace":                     {"type": "keyword"},

            # Value manipulation
            "oldValue":                  {"type": "text"},
            "newValue":                  {"type": "text"},

            # Other fields
            "overlay":                   {"type": "object"},
            "zIndex":                    {"type": "integer"},
            "coverage":                  {"type": "integer"},
            "pageUrl":                   {"type": "keyword"},
            "details":                   {"type": "object"},
            "text":                      {"type": "text"},

            # Summary field
            "summary":                   {"type": "keyword"},

            # Frontend event fields
            "severity":                  {"type": "keyword"},
            "signals":                   {"type": "keyword"},
            "gap":                       {"type": "integer"},
            "first":                     {"type": "date"},
            "last":                      {"type": "date"},

            # Blocking overlay (also uses 'text' field defined above)
            "name":                      {"type": "keyword"},
            # Vue-specific fields
            "msg":                       {"type": "text"},

            # Automation extras
            "rapidClickCount":           {"type": "integer"},
            "connection":                {"type": "object"},
            "element":                   {"type": "keyword"},
            "elementInspection":         {"type": "object"},

            # Queue/transport reliability fields
            "droppedCount":              {"type": "integer"},
            "queueSize":                 {"type": "integer"},
            "retryAttempts":             {"type": "integer"},
            "totalEventsInQueue":        {"type": "integer"},

            # Dialog tracking fields
            "dialogType":                {"type": "keyword"},
            "hasResult":                 {"type": "boolean"},
            "result":                    {"type": "boolean"},

            # Keyboard tracking fields
            "key":                       {"type": "keyword"},
            "keyCode":                   {"type": "keyword"},
            "modifiers":                 {"type": "keyword"},
            "targetElement":             {"type": "keyword"},
            "targetTagName":             {"type": "keyword"},

            # Page load HTTP status
            "httpStatus":                {"type": "integer"},

            # Select element tracking
            "selectedIndex":             {"type": "integer"},
            "input_type":                {"type": "keyword"},

            "_ctx":                      {"type": "object", "enabled": False},
        }
    }
    try:
        if not es.indices.exists(index=INDEX):
            logger.info(f"Creating index '{INDEX}'.")
            es.indices.create(index=INDEX, mappings=mappings)
            logger.info("Index created successfully.")
        else:
            logger.info(f"Index '{INDEX}' already exists. Updating mappings.")
            es.indices.put_mapping(index=INDEX, **mappings)
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

                if "_ctx" in event and isinstance(event.get("_ctx"), dict):
                    ctx = event.pop("_ctx")
                    for k, v in ctx.items():
                        if k not in event:
                            event[k] = v

                event["@timestamp"] = now_utc()

                if "timestamp" in event and event["timestamp"]:
                    normalised = normalise_timestamp(str(event["timestamp"]))
                    if normalised:
                        event["timestamp"] = normalised

                if "time" in event and event["time"]:
                    normalised = normalise_timestamp(str(event["time"]))
                    if normalised:
                        event["time"] = normalised

                if "client_time" in event:
                    normalised = normalise_timestamp(event["client_time"])
                    if normalised:
                        event["client_time"] = normalised
                    else:
                        del event["client_time"]

                batch.append({"_index": INDEX, "_source": event})

        if batch:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Use raise_on_error=False to get errors in response instead of exceptions
                    success, errors = bulk(es, batch, raise_on_error=False)

                    if errors and isinstance(errors, list):
                        # errors is a list of failed item dicts like [{"index": {"error": {...}}}]
                        failed_count = 0
                        failed_reasons = set()
                        failed_docs = []

                        for idx, item in enumerate(errors):
                            if isinstance(item, dict) and "index" in item:
                                error_info = item["index"].get("error")
                                if error_info:
                                    failed_count += 1
                                    err_type = error_info.get('type', 'unknown')
                                    err_reason = error_info.get('reason', 'unknown')[:100]
                                    failed_reasons.add(f"{err_type}: {err_reason}")

                                    # Get the corresponding document from batch
                                    # Note: errors list corresponds to failed items, we requeue all on failure
                                    if idx < len(batch):
                                        doc = batch[idx]["_source"]
                                        logger.error(f"Failed doc #{idx}: {err_type} - {err_reason}. Doc: {json.dumps(doc)[:500]}")
                                        failed_docs.append(doc)

                        if failed_count > 0:
                            logger.warning(f"Bulk index result: {success} succeeded, {failed_count} failed. Reasons: {failed_reasons}")
                            # Re-queue only the failed documents
                            if failed_docs:
                                logger.error(f"Re-queuing {len(failed_docs)} failed events")
                                for doc in failed_docs:
                                    try:
                                        r.lpush(REDIS_QUEUE_KEY + "_failed", json.dumps(doc))
                                    except Exception as queue_err:
                                        logger.error(f"Failed to re-queue event: {queue_err}")
                            # Continue to next batch, don't retry already-failed docs
                            break
                    else:
                        # No errors - success
                        logger.info(f"Successfully indexed {success} documents.")
                        break

                except Exception as e:
                    logger.error(f"Elasticsearch bulk index failed (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(1 * (attempt + 1))
                    else:
                        # On final attempt failure, re-queue all documents
                        logger.error(f"Re-queuing all {len(batch)} documents after {max_retries} attempts")
                        for item in batch:
                            try:
                                r.lpush(REDIS_QUEUE_KEY + "_failed", json.dumps(item["_source"]))
                            except Exception as queue_err:
                                logger.error(f"Failed to re-queue event: {queue_err}")


if __name__ == "__main__":
    process_logs()
