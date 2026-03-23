import requests
import json
import time
import sys
import os

# --- CONFIGURATION ---
KIBANA_URL = "http://kibana:5601"
AUTH = ("elastic", os.getenv("KIBANA_PASSWORD", "changeme"))
INDEX_PATTERN = "selenium-events*"
DASHBOARD_ID = "comprehensive-selenium-dashboard"

session = requests.Session()
session.headers.update({"kbn-xsrf": "true", "Content-Type": "application/json"})
session.auth = AUTH

def wait_for_kibana():
    print("⏳ Waiting for Kibana to be ready...")
    for _ in range(30):
        try:
            res = session.get(f"{KIBANA_URL}/api/status", timeout=5)
            if res.status_code == 200:
                print("✅ Kibana is online.")
                return True
        except requests.exceptions.ConnectionError:
            time.sleep(2)
    print("❌ Could not connect to Kibana.")
    return False

def get_or_create_data_view():
    """Captures the UUID of the data view to ensure visuals link correctly."""
    payload = {
        "data_view": {
            "title": INDEX_PATTERN,
            "name": "Selenium Events View",
            "timeFieldName": "@timestamp"
        }
    }
    # 1. Try create
    res = session.post(f"{KIBANA_URL}/api/data_views/data_view", json=payload)
    if res.status_code == 200:
        dv_id = res.json()['data_view']['id']
        print(f"✅ Created Data View: {dv_id}")
        return dv_id
    
    # 2. If exists or duplicate name, search for the ID
    print("🔍 Searching for existing Data View UUID...")
    get_res = session.get(f"{KIBANA_URL}/api/data_views")
    if get_res.status_code == 200:
        for dv in get_res.json().get('data_view', []):
            if dv.get('title') == INDEX_PATTERN:
                dv_id = dv.get('id')
                print(f"✅ Found existing ID: {dv_id}")
                return dv_id
    
    print(f"❌ Failed to manage Data View: {res.text}")
    sys.exit(1)

def create_vis(vis_id, title, v_type, query, aggs, dv_uuid, params=None):
    """Universal visualization creator for Kibana 8.x"""
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
    if not wait_for_kibana(): sys.exit(1)
    
    dv_uuid = get_or_create_data_view()
    print("📊 Creating Comprehensive Visualizations...")

    # 1. Volume Over Time
    create_vis("v_time", "Events Over Time", "histogram", "", [
        {"id": "1", "type": "count", "schema": "metric"},
        {"id": "2", "type": "date_histogram", "schema": "segment", "params": {"field": "@timestamp", "interval": "auto"}}
    ], dv_uuid)

    # 2. Event Types Pie (Donut)
    create_vis("v_types", "Event Breakdown", "pie", "", [
        {"id": "1", "type": "count", "schema": "metric"},
        {"id": "2", "type": "terms", "schema": "segment", "params": {"field": "type", "size": 10}}
    ], dv_uuid, params={"isDonut": True})

    # 3. Failed Selectors (THE DEBUGGER) - USES .KEYWORD
    create_vis("v_failed_sel", "CRITICAL: Broken Selectors", "table", "found: false AND type: \"dom-query\"", [
        {"id": "1", "type": "count", "schema": "metric"},
        {"id": "2", "type": "terms", "schema": "bucket", "params": {"field": "selector", "size": 10}},
        {"id": "3", "type": "terms", "schema": "bucket", "params": {"field": "url", "size": 10}}
    ], dv_uuid)

    # 3.5 Failed XPaths (THE DEBUGGER) - USES .KEYWORD
    create_vis("v_failed_xpath", "CRITICAL: Broken XPaths", "table", "found: false AND type: \"xpath-query\"", [
        {"id": "1", "type": "count", "schema": "metric"},
        {"id": "2", "type": "terms", "schema": "bucket", "params": {"field": "xpath", "size": 10}},
        {"id": "3", "type": "terms", "schema": "bucket", "params": {"field": "url", "size": 10}}
    ], dv_uuid)

    # 4. JS Error Log - USES .KEYWORD
    create_vis("v_js_err", "JS Runtime Crashes (Detailed)", "table", "type: \"js-error\"", [
        {"id": "1", "type": "count", "schema": "metric"},
        {"id": "2", "type": "terms", "schema": "bucket", "params": {"field": "message.keyword", "size": 10}},
        {"id": "3", "type": "terms", "schema": "bucket", "params": {"field": "source", "size": 10}},
        {"id": "4", "type": "terms", "schema": "bucket", "params": {"field": "lineno", "size": 10}},
        {"id": "5", "type": "terms", "schema": "bucket", "params": {"field": "url", "size": 10}}
    ], dv_uuid)

    # 5. Tag Interactions
    create_vis("v_tags", "Most Interacted Elements", "pie", "", [
        {"id": "1", "type": "count", "schema": "metric"},
        {"id": "2", "type": "terms", "schema": "segment", "params": {"field": "tag", "size": 10}}
    ], dv_uuid)

    print("🏗️  Assembling Dashboard layout...")
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
        print(f"\n🚀 SUCCESS! Dashboard ready at: {KIBANA_URL}/app/dashboards#/view/{DASHBOARD_ID}")
    else:
        print(f"❌ Failed: {res.text}")

if __name__ == "__main__":
    build_dashboard()