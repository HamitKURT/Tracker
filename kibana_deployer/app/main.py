import requests
import json
import logging
import time
import sys
import os
import io
import uuid

logging.basicConfig(level=logging.INFO, format='%(asctime)s - DEPLOYER - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

KIBANA_URL  = os.getenv("KIBANA_URL",  "http://kibana:5601")
ELASTIC_URL = os.getenv("ELASTIC_URL", "http://elasticsearch:9200")

ELASTIC_USERNAME = os.getenv("ELASTIC_USERNAME", "elastic")
ELASTIC_PASSWORD = os.getenv("ELASTIC_PASSWORD", "changeme")
KIBANA_SYSTEM_PASSWORD = os.getenv("KIBANA_PASSWORD", "changeme")

if not KIBANA_SYSTEM_PASSWORD:
    raise ValueError("KIBANA_PASSWORD environment variable is required")

INDEX_PATTERN = "selenium-events*"
DASHBOARD_ID  = "comprehensive-selenium-dashboard"
DATA_VIEW_ID  = "selenium-events-data-view"

# Kibana API sessions must use 'elastic' superuser — kibana_system is a
# service account without management privileges (causes 403 on data view creation).
session = requests.Session()
session.headers.update({"kbn-xsrf": "true"})
session.auth = (ELASTIC_USERNAME, ELASTIC_PASSWORD)

json_session = requests.Session()
json_session.headers.update({"kbn-xsrf": "true", "Content-Type": "application/json"})
json_session.auth = (ELASTIC_USERNAME, ELASTIC_PASSWORD)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Wait for Elasticsearch
# ─────────────────────────────────────────────────────────────────────────────
def wait_for_elasticsearch():
    logger.info("[ES] Waiting for cluster health...")
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
                    logger.info(f"[ES] Ready (status={status})")
                    return
        except Exception as exc:
            logger.warning(f"[ES] {exc} — retrying...")
        time.sleep(5)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Configure kibana_system password
# ─────────────────────────────────────────────────────────────────────────────
def configure_kibana_system():
    wait_for_elasticsearch()
    logger.info("[ES] Waiting for .security index to initialise (30s)...")
    time.sleep(30)

    logger.info("[ES] Setting kibana_system password...")
    res = requests.put(
        f"{ELASTIC_URL}/_security/user/kibana_system/_password",
        auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
        json={"password": KIBANA_SYSTEM_PASSWORD},
    )
    if res.status_code in (200, 204):
        logger.info("[ES] kibana_system configured successfully.")
        mark_elastic_ready()
    else:
        logger.error(f"[ES] Failed: {res.status_code} — {res.text}")
        sys.exit(1)


def mark_elastic_ready():
    with open("/tmp/elastic_ready", "w") as f:
        f.write("ok")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Wait for Kibana
# ─────────────────────────────────────────────────────────────────────────────
def wait_for_kibana():
    logger.info("[Kibana] Waiting for Kibana to become ready...")
    while True:
        try:
            res = session.get(f"{KIBANA_URL}/api/status", timeout=5)
            if res.status_code == 200:
                level = res.json().get("status", {}).get("overall", {}).get("level", "")
                if level == "available":
                    logger.info("[Kibana] Ready.")
                    return
                logger.info(f"[Kibana] Status: {level} — waiting...")
        except Exception as exc:
            logger.warning(f"[Kibana] {exc} — retrying...")
        time.sleep(5)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Create Data View
# ─────────────────────────────────────────────────────────────────────────────
def get_or_create_data_view() -> str:
    logger.info(f"[Kibana] Creating data view: {INDEX_PATTERN}")
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
        logger.info(f"[Kibana] Data view created: {dv_id}")
        return dv_id

    if res.status_code == 400 and "already exists" in res.text:
        logger.info("[Kibana] Data view already exists, searching...")
    else:
        logger.warning(f"[Kibana] Failed to create data view ({res.status_code}): {res.text}")

    get_res = json_session.get(f"{KIBANA_URL}/api/data_views")
    if get_res.status_code == 200:
        for dv in get_res.json().get("data_view", []):
            if dv.get("title") == INDEX_PATTERN:
                dv_id = dv["id"]
                logger.info(f"[Kibana] Found existing data view: {dv_id}")
                return dv_id

    logger.error("[Kibana] Data view not found.")
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
    layer_time = uid(); col_timestamp = uid(); col_count_time = uid()
    v_time  = lens_obj("v_time", "Events Over Time", "lnsXY", layer_time,
        layer=make_layer({
            col_timestamp: {
                "dataType":      "date",
                "isBucketed":    True,
                "label":         "@timestamp",
                "operationType": "date_histogram",
                "params":        {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField":   "@timestamp",
            },
            col_count_time: count_col(),
        }, [col_timestamp, col_count_time], layer_time),
        visualization=xy_visualization(layer_time, col_timestamp, col_count_time),
    )

    # ── 2. Event Breakdown (donut) ────────────────────────────────────────────
    layer_types = uid(); col_event_type = uid(); col_count_types = uid()
    v_types = lens_obj("v_types", "Event Breakdown", "lnsPie", layer_types,
        layer=make_layer({
            col_event_type: terms_col("Event Type", "type", col_count_types),
            col_count_types: count_col(),
        }, [col_event_type, col_count_types], layer_types),
        visualization=pie_visualization(layer_types, col_event_type, col_count_types, shape="donut"),
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
    layer_sel = uid(); col_selector = uid(); col_url_sel = uid(); col_count_sel = uid()
    v_failed_sel = lens_obj("v_failed_sel", "CRITICAL: Broken Selectors", "lnsDatatable", layer_sel,
        layer=make_layer({
            col_selector:  terms_col_all("Selector", "selector", col_count_sel),
            col_url_sel:   terms_col_all("URL",      "url",      col_count_sel),
            col_count_sel: count_col(),
        }, [col_selector, col_url_sel, col_count_sel], layer_sel),
        visualization=datatable_vis(layer_sel, [col_selector, col_url_sel, col_count_sel], col_count_sel),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"bool": {"must": [
                      {"term":  {"found": False}},
                      {"match": {"type": "dom-query"}},
                  ]}}}],
    )

    # ── 4. Broken XPaths (datatable) ─────────────────────────────────────────
    # Columns: xpath | url | count   Filter: found:false AND type:xpath-query
    layer_xpath = uid(); col_xpath_val = uid(); col_url_xpath = uid(); col_count_xpath = uid()
    v_failed_xpath = lens_obj("v_failed_xpath", "CRITICAL: Broken XPaths", "lnsDatatable", layer_xpath,
        layer=make_layer({
            col_xpath_val:   terms_col_all("XPath", "xpath", col_count_xpath),
            col_url_xpath:   terms_col_all("URL",   "url",   col_count_xpath),
            col_count_xpath: count_col(),
        }, [col_xpath_val, col_url_xpath, col_count_xpath], layer_xpath),
        visualization=datatable_vis(layer_xpath, [col_xpath_val, col_url_xpath, col_count_xpath], col_count_xpath),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"bool": {"must": [
                      {"term":  {"found": False}},
                      {"match": {"type": "xpath-query"}},
                  ]}}}],
    )

    # ── 5. JS Runtime Crashes (datatable) ────────────────────────────────────
    # Columns: message | source | url | count | lineno(median)
    # Filter: type:js-error
    layer_err = uid(); col_message = uid(); col_source = uid(); col_url_err = uid(); col_count_err = uid(); col_lineno = uid()
    v_js_err = lens_obj("v_js_err", "JS Runtime Crashes (Detailed)", "lnsDatatable", layer_err,
        layer=make_layer({
            col_message: terms_col_all("Message", "message.keyword", col_count_err),
            col_source:  terms_col_all("Source",  "source",          col_count_err),
            col_url_err: terms_col_all("URL",     "url",             col_count_err),
            col_count_err: count_col(),
            col_lineno: {
                "dataType":      "number",
                "isBucketed":    False,
                "label":         "Line No",
                "operationType": "median",
                "params":        {"emptyAsNull": True},
                "sourceField":   "lineno",
            },
        }, [col_message, col_source, col_url_err, col_count_err, col_lineno], layer_err),
        visualization=datatable_vis(layer_err, [col_message, col_source, col_url_err, col_count_err, col_lineno], col_count_err),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "js-error"}}}],
    )

    # ── 6. Most Interacted Elements (pie) ────────────────────────────────────
    layer_tags = uid(); col_tag = uid(); col_count_tags = uid()
    v_tags  = lens_obj("v_tags", "Most Interacted Elements", "lnsPie", layer_tags,
        layer=make_layer({
            col_tag:        terms_col("Tag", "tag", col_count_tags),
            col_count_tags: count_col(),
        }, [col_tag, col_count_tags], layer_tags),
        visualization=pie_visualization(layer_tags, col_tag, col_count_tags, shape="pie"),
    )

    # ── 7. Performance Overview (datatable) ─────────────────────────────────
    layer_perf = uid(); col_perf_url = uid(); col_dom_loaded = uid(); col_load_complete = uid(); col_fcp = uid(); col_res_count = uid()
    v_perf = lens_obj("v_perf", "Performance Overview", "lnsDatatable", layer_perf,
        layer=make_layer({
            col_perf_url: terms_col_all("URL", "url", col_load_complete),
            col_dom_loaded: {
                "dataType": "number", "isBucketed": False,
                "label": "DOM Loaded (ms)", "operationType": "median",
                "params": {"emptyAsNull": True}, "sourceField": "dom_content_loaded_ms",
            },
            col_load_complete: {
                "dataType": "number", "isBucketed": False,
                "label": "Load Complete (ms)", "operationType": "median",
                "params": {"emptyAsNull": True}, "sourceField": "load_complete_ms",
            },
            col_fcp: {
                "dataType": "number", "isBucketed": False,
                "label": "FCP (ms)", "operationType": "median",
                "params": {"emptyAsNull": True}, "sourceField": "first_contentful_paint_ms",
            },
            col_res_count: {
                "dataType": "number", "isBucketed": False,
                "label": "Resources", "operationType": "median",
                "params": {"emptyAsNull": True}, "sourceField": "resource_count",
            },
        }, [col_perf_url, col_dom_loaded, col_load_complete, col_fcp, col_res_count], layer_perf),
        visualization=datatable_vis(layer_perf, [col_perf_url, col_dom_loaded, col_load_complete, col_fcp, col_res_count], col_load_complete),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "performance"}}}],
    )

    # ── 8. Network Requests (XY bar) ─────────────────────────────────────────
    layer_net = uid(); col_net_ts = uid(); col_net_count = uid()
    v_network = lens_obj("v_network", "Network Requests Over Time", "lnsXY", layer_net,
        layer=make_layer({
            col_net_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_net_count: count_col(),
        }, [col_net_ts, col_net_count], layer_net),
        visualization=xy_visualization(layer_net, col_net_ts, col_net_count),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "network-request"}}}],
    )

    # ── 9. Scroll Depth Distribution (XY bar) ────────────────────────────────
    layer_scroll = uid(); col_scroll_depth = uid(); col_scroll_count = uid()
    v_scroll = lens_obj("v_scroll", "Scroll Depth Distribution", "lnsXY", layer_scroll,
        layer=make_layer({
            col_scroll_depth: {
                "dataType": "number", "isBucketed": True,
                "label": "Max Scroll Depth %", "operationType": "range",
                "params": {
                    "type": "range",
                    "maxBars": "auto",
                    "ranges": [
                        {"from": 0, "to": 25, "label": "0-25%"},
                        {"from": 25, "to": 50, "label": "25-50%"},
                        {"from": 50, "to": 75, "label": "50-75%"},
                        {"from": 75, "to": 101, "label": "75-100%"},
                    ],
                },
                "sourceField": "max_depth_percent",
            },
            col_scroll_count: count_col(),
        }, [col_scroll_depth, col_scroll_count], layer_scroll),
        visualization=xy_visualization(layer_scroll, col_scroll_depth, col_scroll_count, series_type="bar"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "scroll-depth"}}}],
    )

    # ── 10. Console Errors (datatable) ────────────────────────────────────────
    layer_console = uid(); col_console_msg = uid(); col_console_level = uid(); col_console_count = uid()
    v_console = lens_obj("v_console", "Console Errors & Warnings", "lnsDatatable", layer_console,
        layer=make_layer({
            col_console_msg:   terms_col_all("Message", "message.keyword", col_console_count),
            col_console_level: terms_col_all("Level", "level", col_console_count),
            col_console_count: count_col(),
        }, [col_console_msg, col_console_level, col_console_count], layer_console),
        visualization=datatable_vis(layer_console, [col_console_msg, col_console_level, col_console_count], col_console_count),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "console-error"}}}],
    )

    # ── 11. Connection Issues (datatable) ─────────────────────────────────────
    layer_conn = uid(); col_conn_status = uid(); col_conn_url = uid(); col_conn_count = uid()
    v_conn = lens_obj("v_conn", "Connection Issues", "lnsDatatable", layer_conn,
        layer=make_layer({
            col_conn_status: terms_col_all("Status", "status", col_conn_count),
            col_conn_url:    terms_col_all("URL", "url", col_conn_count),
            col_conn_count:  count_col(),
        }, [col_conn_status, col_conn_url, col_conn_count], layer_conn),
        visualization=datatable_vis(layer_conn, [col_conn_status, col_conn_url, col_conn_count], col_conn_count),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "connection"}}}],
    )

    # ── Dashboard ─────────────────────────────────────────────────────────────
    panels = [
        {"panelIndex": "1",  "type": "lens", "panelRefName": "panel_v_time",
         "gridData": {"x": 0,  "y": 0,  "w": 48, "h": 12, "i": "1"},  "embeddableConfig": {}},
        {"panelIndex": "2",  "type": "lens", "panelRefName": "panel_v_types",
         "gridData": {"x": 0,  "y": 12, "w": 24, "h": 12, "i": "2"},  "embeddableConfig": {}},
        {"panelIndex": "3",  "type": "lens", "panelRefName": "panel_v_tags",
         "gridData": {"x": 24, "y": 12, "w": 24, "h": 12, "i": "3"},  "embeddableConfig": {}},
        {"panelIndex": "4",  "type": "lens", "panelRefName": "panel_v_failed_sel",
         "gridData": {"x": 0,  "y": 24, "w": 16, "h": 15, "i": "4"},  "embeddableConfig": {}},
        {"panelIndex": "5",  "type": "lens", "panelRefName": "panel_v_failed_xpath",
         "gridData": {"x": 16, "y": 24, "w": 16, "h": 15, "i": "5"},  "embeddableConfig": {}},
        {"panelIndex": "6",  "type": "lens", "panelRefName": "panel_v_js_err",
         "gridData": {"x": 32, "y": 24, "w": 16, "h": 15, "i": "6"},  "embeddableConfig": {}},
        {"panelIndex": "7",  "type": "lens", "panelRefName": "panel_v_perf",
         "gridData": {"x": 0,  "y": 39, "w": 48, "h": 12, "i": "7"},  "embeddableConfig": {}},
        {"panelIndex": "8",  "type": "lens", "panelRefName": "panel_v_network",
         "gridData": {"x": 0,  "y": 51, "w": 24, "h": 12, "i": "8"},  "embeddableConfig": {}},
        {"panelIndex": "9",  "type": "lens", "panelRefName": "panel_v_scroll",
         "gridData": {"x": 24, "y": 51, "w": 24, "h": 12, "i": "9"},  "embeddableConfig": {}},
        {"panelIndex": "10", "type": "lens", "panelRefName": "panel_v_console",
         "gridData": {"x": 0,  "y": 63, "w": 24, "h": 12, "i": "10"}, "embeddableConfig": {}},
        {"panelIndex": "11", "type": "lens", "panelRefName": "panel_v_conn",
         "gridData": {"x": 24, "y": 63, "w": 24, "h": 12, "i": "11"}, "embeddableConfig": {}},
    ]

    dashboard = {
        "type":    "dashboard",
        "id":      DASHBOARD_ID,
        "managed": False,
        "attributes": {
            "title":       "Comprehensive Selenium Telemetry Dashboard",
            "description": "Full view of bot behaviour, site errors, performance, and network activity",
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
            {"name": "panel_v_perf",         "type": "lens", "id": "v_perf"},
            {"name": "panel_v_network",      "type": "lens", "id": "v_network"},
            {"name": "panel_v_scroll",       "type": "lens", "id": "v_scroll"},
            {"name": "panel_v_console",      "type": "lens", "id": "v_console"},
            {"name": "panel_v_conn",         "type": "lens", "id": "v_conn"},
        ],
        "coreMigrationVersion": "8.8.0",
    }

    objects = [v_time, v_types, v_failed_sel, v_failed_xpath, v_js_err, v_tags,
               v_perf, v_network, v_scroll, v_console, v_conn, dashboard]
    return "\n".join(json.dumps(obj) for obj in objects)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Import via _import API
# ─────────────────────────────────────────────────────────────────────────────
def import_saved_objects(ndjson: str):
    logger.info("[Kibana] Importing saved objects via _import API...")
    files = {
        "file": ("export.ndjson", io.BytesIO(ndjson.encode("utf-8")), "application/ndjson")
    }
    res = session.post(
        f"{KIBANA_URL}/api/saved_objects/_import?overwrite=true",
        files=files,
    )
    logger.info(f"[Kibana] _import response: HTTP {res.status_code}")

    if res.status_code in (200, 201):
        body    = res.json()
        success = body.get("success", False)
        count   = body.get("successCount", 0)
        errors  = body.get("errors", [])
        if success:
            logger.info(f"[Kibana] Import successful — {count} object(s) created/updated.")
        else:
            logger.warning(f"[Kibana] Import partially successful ({count} object(s)). Errors:")
            for err in errors:
                logger.warning(f"  - {err.get('type')}/{err.get('id')}: {json.dumps(err.get('error', {}))}")
    else:
        logger.error(f"[Kibana] Import failed ({res.status_code}):\n{res.text}")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def build_dashboard():
    wait_for_kibana()
    dv_id = get_or_create_data_view()
    ndjson = build_ndjson(dv_id)
    import_saved_objects(ndjson)
    logger.info(f"[Kibana] Dashboard ready -> {KIBANA_URL}/app/dashboards#/view/{DASHBOARD_ID}")


if __name__ == "__main__":
    configure_kibana_system()
    build_dashboard()

    while True:
        time.sleep(60)