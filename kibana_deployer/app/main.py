import requests
import json
import time
import sys
import os
import io
import uuid

KIBANA_URL  = os.getenv("KIBANA_URL",  "http://kibana:5601")
ELASTIC_URL = os.getenv("ELASTIC_URL", "http://elasticsearch:9200")

KIBANA_USERNAME  = os.getenv("KIBANA_USERNAME", "kibana_system")
KIBANA_PASSWORD  = os.getenv("KIBANA_PASSWORD", "changeme")
ELASTIC_USERNAME = os.getenv("ELASTIC_USERNAME", "elastic")
ELASTIC_PASSWORD = os.getenv("ELASTIC_PASSWORD", "changeme")

if not KIBANA_PASSWORD:
    raise ValueError("KIBANA_PASSWORD environment variable is required")

INDEX_PATTERN = "selenium-events*"
DASHBOARD_ID  = "comprehensive-selenium-dashboard"
DATA_VIEW_ID  = "selenium-events-data-view"

session = requests.Session()
session.headers.update({"kbn-xsrf": "true"})
session.auth = (KIBANA_USERNAME, KIBANA_PASSWORD)

json_session = requests.Session()
json_session.headers.update({"kbn-xsrf": "true", "Content-Type": "application/json"})
json_session.auth = (KIBANA_USERNAME, KIBANA_PASSWORD)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Wait for Elasticsearch
# ─────────────────────────────────────────────────────────────────────────────
def wait_for_elasticsearch():
    print("[ES] Waiting for cluster health...")
    time.sleep(10)
    while True:
        try:
            res = requests.get(
                f"{ELASTIC_URL}/_cluster/health",
                auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
                timeout=5,
            )
            if res.status_code == 200:
                status = res.json().get("status")
                if status in ("yellow", "green"):
                    print(f"[ES] Ready (status={status})")
                    return
        except Exception as exc:
            print(f"[ES] {exc} — retrying...")
        time.sleep(5)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Configure kibana_system password
# ─────────────────────────────────────────────────────────────────────────────
def configure_kibana_system():
    wait_for_elasticsearch()
    print("[ES] Waiting for .security index to initialise (30s)...")
    time.sleep(30)

    print("[ES] Setting kibana_system password...")
    res = requests.put(
        f"{ELASTIC_URL}/_security/user/kibana_system/_password",
        auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
        json={"password": KIBANA_PASSWORD},
    )
    if res.status_code in (200, 204):
        print("[ES] kibana_system configured successfully.")
        mark_elastic_ready()
    else:
        print(f"[ES] Failed: {res.status_code} — {res.text}")
        sys.exit(1)


def mark_elastic_ready():
    with open("/tmp/elastic_ready", "w") as f:
        f.write("ok")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Wait for Kibana
# ─────────────────────────────────────────────────────────────────────────────
def wait_for_kibana():
    print("[Kibana] Waiting for Kibana to become ready...")
    while True:
        try:
            res = session.get(f"{KIBANA_URL}/api/status", timeout=5)
            if res.status_code == 200:
                level = res.json().get("status", {}).get("overall", {}).get("level", "")
                if level == "available":
                    print("[Kibana] Ready.")
                    return
                print(f"[Kibana] Status: {level} — waiting...")
        except Exception as exc:
            print(f"[Kibana] {exc} — retrying...")
        time.sleep(5)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Create Data View
# ─────────────────────────────────────────────────────────────────────────────
def get_or_create_data_view() -> str:
    print(f"[Kibana] Creating data view: {INDEX_PATTERN}")
    payload = {
        "data_view": {
            "id":            DATA_VIEW_ID,
            "title":         INDEX_PATTERN,
            "name":          "Selenium Events View",
            "timeFieldName": "@timestamp",
        },
        "override": True,
    }
    res = json_session.post(f"{KIBANA_URL}/api/data_views/data_view", json=payload)
    if res.status_code in (200, 201):
        dv_id = res.json()["data_view"]["id"]
        print(f"[Kibana] Data view created: {dv_id}")
        return dv_id

    if res.status_code == 400 and "already exists" in res.text:
        print("[Kibana] Data view already exists, searching...")
    else:
        print(f"[Kibana] Failed to create data view ({res.status_code}): {res.text}")

    get_res = json_session.get(f"{KIBANA_URL}/api/data_views")
    if get_res.status_code == 200:
        for dv in get_res.json().get("data_view", []):
            if dv.get("title") == INDEX_PATTERN:
                dv_id = dv["id"]
                print(f"[Kibana] Found existing data view: {dv_id}")
                return dv_id

    print("[Kibana] Data view not found.")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Build NDJSON
#
#    Format derived from a real Kibana 9.3.2 export. Key requirements:
#    - typeMigrationVersion: "10.1.0"  ← migration transformer checks this
#    - coreMigrationVersion: "8.8.0"
#    - datasourceStates must include "indexpattern" and "textBased" empty dicts
#    - each layer needs: incompleteColumns, sampling, columnOrder
#    - visualization.layers is an ARRAY with colorMapping, position, showGridlines
#    - internalReferences: [] required at state level
#    - reference name: "indexpattern-datasource-layer-{layerId}"
#    - layer IDs must be UUIDs (not plain strings like "layer1")
# ─────────────────────────────────────────────────────────────────────────────
def build_ndjson(dv_id: str) -> str:

    def uid():
        return str(uuid.uuid4())

    def make_layer(columns: dict, column_order: list, layer_id: str) -> dict:
        """Single formBased layer matching real Kibana 9.3.2 export format."""
        return {
            "columnOrder":       column_order,
            "columns":           columns,
            "incompleteColumns": {},
            "sampling":          1,
        }

    def count_col():
        return {
            "dataType":      "number",
            "isBucketed":    False,
            "label":         "Count of records",
            "operationType": "count",
            "params":        {"emptyAsNull": True},
            "sourceField":   "___records___",
        }

    def terms_col(label, field, metric_col_id, size=10):
        return {
            "dataType":      "string",
            "isBucketed":    True,
            "label":         label,
            "operationType": "terms",
            "params": {
                "size":           size,
                "orderBy":        {"type": "column", "columnId": metric_col_id},
                "orderDirection": "desc",
                "otherBucket":    True,
                "missingBucket":  False,
                "parentFormat":   {"id": "terms"},
            },
            "sourceField": field,
        }

    def lens_obj(vis_id, title, vis_type, layer_id, layer, visualization, filters=None):
        """
        Envelope matching real Kibana 9.3.2 lens saved-object export.
        typeMigrationVersion "10.1.0" is critical — without it the migration
        transformer crashes trying to upcast the document.
        """
        return {
            "type":    "lens",
            "id":      vis_id,
            "managed": False,
            "attributes": {
                "description":   "",
                "title":         title,
                "version":       1,
                "visualizationType": vis_type,
                "state": {
                    "adHocDataViews":    {},
                    "internalReferences": [],
                    "filters":           filters or [],
                    "query":             {"language": "kuery", "query": ""},
                    "datasourceStates": {
                        "formBased": {
                            "layers": {layer_id: layer}
                        },
                        # These empty dicts are present in real exports
                        "indexpattern": {"layers": {}},
                        "textBased":    {"layers": {}},
                    },
                    "visualization": visualization,
                },
            },
            "references": [{
                "id":   dv_id,
                "name": f"indexpattern-datasource-layer-{layer_id}",
                "type": "index-pattern",
            }],
            # Both migration version fields are required
            "coreMigrationVersion": "8.8.0",
            "typeMigrationVersion": "10.1.0",
        }

    def xy_visualization(layer_id, x_col_id, y_col_id, series_type="bar_stacked"):
        return {
            "axisTitlesVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
            "fittingFunction": "Linear",
            "gridlinesVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
            "labelsOrientation": {"x": 0, "yLeft": 0, "yRight": 0},
            "layers": [{
                "accessors":   [y_col_id],
                "colorMapping": {
                    "assignments": [],
                    "colorMode":   {"type": "categorical"},
                    "paletteId":   "default",
                    "specialAssignments": [{
                        "color": {"type": "loop"},
                        "rules": [{"type": "other"}],
                        "touched": False,
                    }],
                },
                "layerId":      layer_id,
                "layerType":    "data",
                "position":     "top",
                "seriesType":   series_type,
                "showGridlines": False,
                "xAccessor":    x_col_id,
            }],
            "legend":                    {"isVisible": True, "position": "right"},
            "preferredSeriesType":       series_type,
            "tickLabelsVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
            "valueLabels": "hide",
        }

    def pie_visualization(layer_id, group_col_id, metric_col_id, shape="donut"):
        return {
            "shape": shape,
            "layers": [{
                "layerId":         layer_id,
                "layerType":       "data",
                "primaryGroups":   [group_col_id],
                "metrics":         [metric_col_id],
                "numberDisplay":   "percent",
                "categoryDisplay": "default",
                "legendDisplay":   "default",
                "nestedLegend":    False,
            }],
        }

    def datatable_visualization(layer_id, col_ids):
        return {
            "layers": [{
                "layerId":   layer_id,
                "layerType": "data",
                "columns":   [{"columnId": c, "isTransposed": False} for c in col_ids],
                "sorting":   {"columnId": col_ids[-1], "direction": "desc"},
            }],
            "rowHeight":        "single",
            "rowHeightLines":   1,
            "headerRowHeight":  "single",
            "headerRowHeightLines": 1,
        }

    # ── 1. Events Over Time (XY bar) ─────────────────────────────────────────
    l1      = uid(); c_ts = uid(); c_cnt1 = uid()
    v_time  = lens_obj("v_time", "Events Over Time", "lnsXY", l1,
        layer=make_layer({
            c_ts: {
                "dataType":      "date",
                "isBucketed":    True,
                "label":         "@timestamp",
                "operationType": "date_histogram",
                "params":        {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField":   "@timestamp",
            },
            c_cnt1: count_col(),
        }, [c_ts, c_cnt1], l1),
        visualization=xy_visualization(l1, c_ts, c_cnt1),
    )

    # ── 2. Event Breakdown (donut) ────────────────────────────────────────────
    l2      = uid(); c_type = uid(); c_cnt2 = uid()
    v_types = lens_obj("v_types", "Event Breakdown", "lnsPie", l2,
        layer=make_layer({
            c_type: terms_col("Event Type", "type", c_cnt2),
            c_cnt2: count_col(),
        }, [c_type, c_cnt2], l2),
        visualization=pie_visualization(l2, c_type, c_cnt2, shape="donut"),
    )

    # ── Helper: terms column with full record count (size:10000, no "Other" bucket)
    def terms_col_all(label, field, order_col):
        return {
            "dataType":      "string",
            "isBucketed":    True,
            "label":         label,
            "operationType": "terms",
            "params": {
                "size":           10000,
                "orderBy":        {"type": "column", "columnId": order_col},
                "orderDirection": "desc",
                "otherBucket":    False,
                "missingBucket":  False,
                "parentFormat":   {"id": "terms"},
                "include": [], "includeIsRegex": False,
                "exclude": [], "excludeIsRegex": False,
            },
            "sourceField": field,
        }

    def datatable_vis(layer_id, col_ids, sort_col):
        return {
            "layerId":              layer_id,
            "layerType":            "data",
            "columns":              [{"columnId": c, "isTransposed": False} for c in col_ids],
            "sorting":              {"columnId": sort_col, "direction": "desc"},
            "rowHeight":            "single",
            "rowHeightLines":       1,
            "headerRowHeight":      "single",
            "headerRowHeightLines": 1,
        }

    # ── 3. Broken Selectors (datatable) ──────────────────────────────────────
    # Columns: selector | url | count   Filter: found:false AND type:dom-query
    l3 = uid(); c_sel = uid(); c_url3 = uid(); c_cnt3 = uid()
    v_failed_sel = lens_obj("v_failed_sel", "CRITICAL: Broken Selectors", "lnsDatatable", l3,
        layer=make_layer({
            c_sel:  terms_col_all("Selector", "selector", c_cnt3),
            c_url3: terms_col_all("URL",      "url",      c_cnt3),
            c_cnt3: count_col(),
        }, [c_sel, c_url3, c_cnt3], l3),
        visualization=datatable_vis(l3, [c_sel, c_url3, c_cnt3], c_cnt3),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"bool": {"must": [
                      {"term":  {"found": False}},
                      {"match": {"type": "dom-query"}},
                  ]}}}],
    )

    # ── 4. Broken XPaths (datatable) ─────────────────────────────────────────
    # Columns: xpath | url | count   Filter: found:false AND type:xpath-query
    l4 = uid(); c_xp = uid(); c_url4 = uid(); c_cnt4 = uid()
    v_failed_xpath = lens_obj("v_failed_xpath", "CRITICAL: Broken XPaths", "lnsDatatable", l4,
        layer=make_layer({
            c_xp:   terms_col_all("XPath", "xpath", c_cnt4),
            c_url4: terms_col_all("URL",   "url",   c_cnt4),
            c_cnt4: count_col(),
        }, [c_xp, c_url4, c_cnt4], l4),
        visualization=datatable_vis(l4, [c_xp, c_url4, c_cnt4], c_cnt4),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"bool": {"must": [
                      {"term":  {"found": False}},
                      {"match": {"type": "xpath-query"}},
                  ]}}}],
    )

    # ── 5. JS Runtime Crashes (datatable) ────────────────────────────────────
    # Columns: message | source | url | count | lineno(median)
    # Filter: type:js-error
    l5 = uid(); c_msg = uid(); c_src = uid(); c_url5 = uid(); c_cnt5 = uid(); c_ln = uid()
    v_js_err = lens_obj("v_js_err", "JS Runtime Crashes (Detailed)", "lnsDatatable", l5,
        layer=make_layer({
            c_msg:  terms_col_all("Message", "message.keyword", c_cnt5),
            c_src:  terms_col_all("Source",  "source",          c_cnt5),
            c_url5: terms_col_all("URL",     "url",             c_cnt5),
            c_cnt5: count_col(),
            c_ln: {
                "dataType":      "number",
                "isBucketed":    False,
                "label":         "Line No",
                "operationType": "median",
                "params":        {"emptyAsNull": True},
                "sourceField":   "lineno",
            },
        }, [c_msg, c_src, c_url5, c_cnt5, c_ln], l5),
        visualization=datatable_vis(l5, [c_msg, c_src, c_url5, c_cnt5, c_ln], c_cnt5),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "js-error"}}}],
    )

    # ── 6. Most Interacted Elements (pie) ────────────────────────────────────
    l6      = uid(); c_tag = uid(); c_cnt6 = uid()
    v_tags  = lens_obj("v_tags", "Most Interacted Elements", "lnsPie", l6,
        layer=make_layer({
            c_tag:  terms_col("Tag", "tag", c_cnt6),
            c_cnt6: count_col(),
        }, [c_tag, c_cnt6], l6),
        visualization=pie_visualization(l6, c_tag, c_cnt6, shape="pie"),
    )

    # ── Dashboard ─────────────────────────────────────────────────────────────
    panels = [
        {"panelIndex": "1", "type": "lens", "panelRefName": "panel_v_time",
         "gridData": {"x": 0,  "y": 0,  "w": 48, "h": 12, "i": "1"}, "embeddableConfig": {}},
        {"panelIndex": "2", "type": "lens", "panelRefName": "panel_v_types",
         "gridData": {"x": 0,  "y": 12, "w": 24, "h": 12, "i": "2"}, "embeddableConfig": {}},
        {"panelIndex": "3", "type": "lens", "panelRefName": "panel_v_tags",
         "gridData": {"x": 24, "y": 12, "w": 24, "h": 12, "i": "3"}, "embeddableConfig": {}},
        {"panelIndex": "4", "type": "lens", "panelRefName": "panel_v_failed_sel",
         "gridData": {"x": 0,  "y": 24, "w": 16, "h": 15, "i": "4"}, "embeddableConfig": {}},
        {"panelIndex": "5", "type": "lens", "panelRefName": "panel_v_failed_xpath",
         "gridData": {"x": 16, "y": 24, "w": 16, "h": 15, "i": "5"}, "embeddableConfig": {}},
        {"panelIndex": "6", "type": "lens", "panelRefName": "panel_v_js_err",
         "gridData": {"x": 32, "y": 24, "w": 16, "h": 15, "i": "6"}, "embeddableConfig": {}},
    ]

    dashboard = {
        "type":    "dashboard",
        "id":      DASHBOARD_ID,
        "managed": False,
        "attributes": {
            "title":       "Comprehensive Selenium Telemetry Dashboard",
            "description": "Full view of bot behaviour and site errors",
            "panelsJSON":  json.dumps(panels),
            "optionsJSON": json.dumps({
                "useMargins":      True,
                "syncColors":      False,
                "hidePanelTitles": False,
            }),
            "timeRestore": False,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({
                    "query":  {"query": "", "language": "kuery"},
                    "filter": [],
                })
            },
            "version": 1,
        },
        "references": [
            {"name": "panel_v_time",         "type": "lens", "id": "v_time"},
            {"name": "panel_v_types",        "type": "lens", "id": "v_types"},
            {"name": "panel_v_tags",         "type": "lens", "id": "v_tags"},
            {"name": "panel_v_failed_sel",   "type": "lens", "id": "v_failed_sel"},
            {"name": "panel_v_failed_xpath", "type": "lens", "id": "v_failed_xpath"},
            {"name": "panel_v_js_err",       "type": "lens", "id": "v_js_err"},
        ],
        "coreMigrationVersion": "8.8.0",
    }

    objects = [v_time, v_types, v_failed_sel, v_failed_xpath, v_js_err, v_tags, dashboard]
    return "\n".join(json.dumps(obj) for obj in objects)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Import via _import API
# ─────────────────────────────────────────────────────────────────────────────
def import_saved_objects(ndjson: str):
    print("[Kibana] Importing saved objects via _import API...")
    files = {
        "file": ("export.ndjson", io.BytesIO(ndjson.encode("utf-8")), "application/ndjson")
    }
    res = session.post(
        f"{KIBANA_URL}/api/saved_objects/_import?overwrite=true",
        files=files,
    )
    print(f"[Kibana] _import response: HTTP {res.status_code}")

    if res.status_code in (200, 201):
        body    = res.json()
        success = body.get("success", False)
        count   = body.get("successCount", 0)
        errors  = body.get("errors", [])
        if success:
            print(f"[Kibana] Import successful — {count} object(s) created/updated.")
        else:
            print(f"[Kibana] Import partially successful ({count} object(s)). Errors:")
            for err in errors:
                print(f"  ✗ {err.get('type')}/{err.get('id')}: {json.dumps(err.get('error', {}))}")
    else:
        print(f"[Kibana] Import failed ({res.status_code}):\n{res.text}")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def build_dashboard():
    wait_for_kibana()
    dv_id = get_or_create_data_view()
    ndjson = build_ndjson(dv_id)
    import_saved_objects(ndjson)
    print(f"\n[Kibana] Dashboard ready → {KIBANA_URL}/app/dashboards#/view/{DASHBOARD_ID}\n")


if __name__ == "__main__":
    configure_kibana_system()
    build_dashboard()

    while True:
        time.sleep(60)