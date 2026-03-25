import requests
import json
import time
import sys
import os

KIBANA_URL = os.getenv("KIBANA_URL", "http://kibana:5601")
KIBANA_USERNAME = os.getenv("KIBANA_USERNAME", "kibana_system")
KIBANA_PASSWORD = os.getenv("KIBANA_PASSWORD", "changeme")
ELASTIC_URL =  os.getenv("ELASTIC_URL", "http://elasticsearch:9200")
ELASTIC_USERNAME = os.getenv("ELASTIC_USERNAME", "elastic")
ELASTIC_PASSWORD = os.getenv("ELASTIC_PASSWORD", "changeme")

if not KIBANA_PASSWORD:
    raise ValueError("KIBANA_PASSWORD environment variable is required")

AUTH = (KIBANA_USERNAME, KIBANA_PASSWORD)
INDEX_PATTERN = "selenium-events*"
DASHBOARD_ID = "comprehensive-selenium-dashboard"

session = requests.Session()
session.headers.update({"kbn-xsrf": "true", "Content-Type": "application/json"})
session.auth = AUTH

def wait_for_elasticsearch():
    print("Waiting for Elasticsearch to be fully ready...")
    time.sleep(15)
    while True:
        try:
            res = requests.get(
                f"{ELASTIC_URL}/_cluster/health",
                auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
                timeout=5
            )

            if res.status_code == 200:
                status = res.json().get("status")
                if status in ["yellow", "green"]:
                    print(f"Elasticsearch is ready (status={status})")
                    break
        except Exception as e:
            print(f"{e}")
            print("Waiting Elasticsearch")
            time.sleep(5)


def configure_kibana_system():
    wait_for_elasticsearch()

    print("Waiting for security index to be ready...")
    time.sleep(30)

    print("Setting kibana_system password...")

    payload = {
        "password": KIBANA_PASSWORD
    }

    res = requests.put(
        f"{ELASTIC_URL}/_security/user/kibana_system/_password",
        auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
        json=payload
    )

    if res.status_code in [200, 204]:
        print("Kibana_system user configured successfully!")
        mark_elastic_ready()
    else:
        print(f"Failed to configure kibana_system: {res.text}")
        sys.exit(1)

def mark_elastic_ready():
    with open("/tmp/elastic_ready", "w") as f:
        f.write("ok")

def wait_for_kibana():
    print("Waiting for Kibana to be ready...")
    while True:
        try:
            res = session.get(f"{KIBANA_URL}/api/status", timeout=5)
            if res.status_code == 200:
                print("Kibana is online.")
                break
        except Exception:
            print("Waiting Kibana")
            time.sleep(2)

def get_or_create_data_view():
    payload = {
        "data_view": {
            "title": INDEX_PATTERN,
            "name": "Selenium Events View",
            "timeFieldName": "@timestamp"
        }
    }
    res = session.post(f"{KIBANA_URL}/api/data_views/data_view", json=payload)
    if res.status_code == 200:
        dv_id = res.json()['data_view']['id']
        print(f"Created Data View: {dv_id}")
        return dv_id
    
    print("Searching for existing Data View UUID...")
    get_res = session.get(f"{KIBANA_URL}/api/data_views")
    if get_res.status_code == 200:
        for dv in get_res.json().get('data_view', []):
            if dv.get('title') == INDEX_PATTERN:
                dv_id = dv.get('id')
                print(f"Found existing ID: {dv_id}")
                return dv_id
    
    print(f"Failed to manage Data View: {res.text}")
    sys.exit(1)

def create_vis(vis_id, title, v_type, query, aggs, dv_uuid, params=None):
    vis_state = {
        "title": title,
        "type": v_type,
        "params": params or {"addTooltip": True, "addLegend": True},
        "aggs": aggs
    }
    
    payload = {
        "attributes": {
            "title": title,
            "visState": json.dumps(vis_state),
            "uiStateJSON": "{}",
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({
                    "query": {"query": query, "language": "kuery"},
                    "filter": [],
                    "indexRefName": "kibanaSavedObjectMeta.searchSourceJSON.index"
                })
            }
        },
        "references": [
            {"id": dv_uuid, "type": "index-pattern", "name": "kibanaSavedObjectMeta.searchSourceJSON.index"}
        ]
    }
    
    endpoint = f"{KIBANA_URL}/api/saved_objects/visualization/{vis_id}?overwrite=true"
    res = session.post(endpoint, json=payload)
    return res.status_code

def build_dashboard():
    wait_for_kibana()
    
    dv_uuid = get_or_create_data_view()
    print("Creating Comprehensive Visualizations...")

    create_vis("v_time", "Events Over Time", "histogram", "", [
        {"id": "1", "type": "count", "schema": "metric"},
        {"id": "2", "type": "date_histogram", "schema": "segment", "params": {"field": "@timestamp", "interval": "auto"}}
    ], dv_uuid)

    create_vis("v_types", "Event Breakdown", "pie", "", [
        {"id": "1", "type": "count", "schema": "metric"},
        {"id": "2", "type": "terms", "schema": "segment", "params": {"field": "type", "size": 10}}
    ], dv_uuid, params={"isDonut": True})

    create_vis("v_failed_sel", "CRITICAL: Broken Selectors", "table", "found: false AND type: \"dom-query\"", [
        {"id": "1", "type": "count", "schema": "metric"},
        {"id": "2", "type": "terms", "schema": "bucket", "params": {"field": "selector", "size": 10}},
        {"id": "3", "type": "terms", "schema": "bucket", "params": {"field": "url", "size": 10}}
    ], dv_uuid)

    create_vis("v_failed_xpath", "CRITICAL: Broken XPaths", "table", "found: false AND type: \"xpath-query\"", [
        {"id": "1", "type": "count", "schema": "metric"},
        {"id": "2", "type": "terms", "schema": "bucket", "params": {"field": "xpath", "size": 10}},
        {"id": "3", "type": "terms", "schema": "bucket", "params": {"field": "url", "size": 10}}
    ], dv_uuid)

    create_vis("v_js_err", "JS Runtime Crashes (Detailed)", "table", "type: \"js-error\"", [
        {"id": "1", "type": "count", "schema": "metric"},
        {"id": "2", "type": "terms", "schema": "bucket", "params": {"field": "message.keyword", "size": 10}},
        {"id": "3", "type": "terms", "schema": "bucket", "params": {"field": "source", "size": 10}},
        {"id": "4", "type": "terms", "schema": "bucket", "params": {"field": "lineno", "size": 10}},
        {"id": "5", "type": "terms", "schema": "bucket", "params": {"field": "url", "size": 10}}
    ], dv_uuid)

    create_vis("v_tags", "Most Interacted Elements", "pie", "", [
        {"id": "1", "type": "count", "schema": "metric"},
        {"id": "2", "type": "terms", "schema": "segment", "params": {"field": "tag", "size": 10}}
    ], dv_uuid)

    print("Assembling Dashboard layout...")
    dash_payload = {
        "attributes": {
            "title": "Comprehensive Selenium Telemetry Dashboard",
            "description": "Full view of Bot behavior and site errors",
            "panelsJSON": json.dumps([
                {"gridData": {"x": 0, "y": 0, "w": 48, "h": 12}, "panelIndex": "1", "panelRefName": "p1"},
                {"gridData": {"x": 0, "y": 12, "w": 24, "h": 12}, "panelIndex": "2", "panelRefName": "p2"},
                {"gridData": {"x": 24, "y": 12, "w": 24, "h": 12}, "panelIndex": "3", "panelRefName": "p3"},
                {"gridData": {"x": 0, "y": 24, "w": 16, "h": 15}, "panelIndex": "4", "panelRefName": "p4"},
                {"gridData": {"x": 16, "y": 24, "w": 16, "h": 15}, "panelIndex": "6", "panelRefName": "p6"},
                {"gridData": {"x": 32, "y": 24, "w": 16, "h": 15}, "panelIndex": "5", "panelRefName": "p5"}
            ]),
            "optionsJSON": json.dumps({"darkTheme": True, "useMargins": True}),
            "timeRestore": False,
            "kibanaSavedObjectMeta": {"searchSourceJSON": '{"query":{"query":"","language":"kuery"},"filter":[]}'}
        },
        "references": [
            {"name": "p1", "type": "visualization", "id": "v_time"},
            {"name": "p2", "type": "visualization", "id": "v_types"},
            {"name": "p3", "type": "visualization", "id": "v_tags"},
            {"name": "p4", "type": "visualization", "id": "v_failed_sel"},
            {"name": "p5", "type": "visualization", "id": "v_js_err"},
            {"name": "p6", "type": "visualization", "id": "v_failed_xpath"}
        ]
    }

    res = session.post(f"{KIBANA_URL}/api/saved_objects/dashboard/{DASHBOARD_ID}?overwrite=true", json=dash_payload)
    if res.status_code in [200, 201, 409]:
        print(f"\nSUCCESS! Dashboard ready at: {KIBANA_URL}/app/dashboards#/view/{DASHBOARD_ID}")
    else:
        print(f"Failed: {res.text}")

if __name__ == "__main__":
    configure_kibana_system()

    build_dashboard()

    while True:
        time.sleep(60)
