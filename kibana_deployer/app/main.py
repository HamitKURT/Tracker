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

    # ── 9. Timing Alerts (suspicious click intervals) ─────────────────────────
    layer_timing = uid(); col_timing_event = uid(); col_timing_interval = uid(); col_timing_count = uid()
    v_timing = lens_obj("v_timing", "CRITICAL: Timing Alerts (Bot Detection)", "lnsDatatable", layer_timing,
        layer=make_layer({
            col_timing_event:   terms_col("Event", "event", col_timing_count),
            col_timing_interval: {
                "dataType": "number", "isBucketed": False,
                "label": "Interval (ms)", "operationType": "median",
                "params": {"emptyAsNull": True}, "sourceField": "interval_ms",
            },
            col_timing_count:  count_col(),
        }, [col_timing_event, col_timing_interval, col_timing_count], layer_timing),
        visualization=datatable_vis(layer_timing, [col_timing_event, col_timing_interval, col_timing_count], col_timing_interval),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "timing-alert"}}}],
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

    # ── 11. Connection Issues (pie chart) ─────────────────────────────────────
    layer_conn = uid(); col_conn_status = uid(); col_conn_count = uid()
    v_conn = lens_obj("v_conn", "Connection Status Distribution", "lnsPie", layer_conn,
        layer=make_layer({
            col_conn_status: terms_col("Status", "status", col_conn_count),
            col_conn_count:  count_col(),
        }, [col_conn_status, col_conn_count], layer_conn),
        visualization=pie_visualization(layer_conn, col_conn_status, col_conn_count, shape="donut"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "connection"}}}],
    )

    # ── 12. Element Inspection - Method Breakdown (pie) ───────────────────────
    layer_elem = uid(); col_elem_method = uid(); col_elem_count = uid()
    v_elem = lens_obj("v_elem", "Element Inspection Methods", "lnsPie", layer_elem,
        layer=make_layer({
            col_elem_method: terms_col("Method", "method", col_elem_count),
            col_elem_count:   count_col(),
        }, [col_elem_method, col_elem_count], layer_elem),
        visualization=pie_visualization(layer_elem, col_elem_method, col_elem_count, shape="pie"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "element-inspection"}}}],
    )

    # ── 13. Element Action Events - Tag Distribution (pie) ────────────────────
    layer_elem_act = uid(); col_elem_act_tag = uid(); col_elem_act_count = uid()
    v_elem_act = lens_obj("v_elem_act", "Element Actions by Tag Type", "lnsPie", layer_elem_act,
        layer=make_layer({
            col_elem_act_tag:   terms_col("Tag", "tag", col_elem_act_count),
            col_elem_act_count: count_col(),
        }, [col_elem_act_tag, col_elem_act_count], layer_elem_act),
        visualization=pie_visualization(layer_elem_act, col_elem_act_tag, col_elem_act_count, shape="donut"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "element-action"}}}],
    )

    # ── 14. Automation Detection Alerts (pie) ─────────────────────────────────
    layer_auto = uid(); col_auto_severity = uid(); col_auto_count = uid()
    v_auto = lens_obj("v_auto", "Automation Severity Distribution", "lnsPie", layer_auto,
        layer=make_layer({
            col_auto_severity: terms_col("Severity", "severity", col_auto_count),
            col_auto_count:    count_col(),
        }, [col_auto_severity, col_auto_count], layer_auto),
        visualization=pie_visualization(layer_auto, col_auto_severity, col_auto_count, shape="donut"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "automation-detected"}}}],
    )

    # ── 15. MutationObserver Events Over Time (XY) ───────────────────────────
    layer_mut = uid(); col_mut_ts = uid(); col_mut_count_total = uid()
    v_mut = lens_obj("v_mut", "MutationObserver Activity Over Time", "lnsXY", layer_mut,
        layer=make_layer({
            col_mut_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_mut_count_total: count_col(),
        }, [col_mut_ts, col_mut_count_total], layer_mut),
        visualization=xy_visualization(layer_mut, col_mut_ts, col_mut_count_total, series_type="area"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "mutation-observer"}}}],
    )

    # ── 16. Data Extraction - Method Breakdown (pie) ────────────────────────
    layer_data = uid(); col_data_method = uid(); col_data_count = uid()
    v_data = lens_obj("v_data", "Data Extraction Methods", "lnsPie", layer_data,
        layer=make_layer({
            col_data_method: terms_col("Method", "method", col_data_count),
            col_data_count:  count_col(),
        }, [col_data_method, col_data_count], layer_data),
        visualization=pie_visualization(layer_data, col_data_method, col_data_count, shape="pie"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "data-extraction"}}}],
    )

    # ── 17. Value Manipulation Methods (pie) ─────────────────────────────────
    layer_val = uid(); col_val_method = uid(); col_val_count = uid()
    v_val = lens_obj("v_val", "Value Manipulation Methods", "lnsPie", layer_val,
        layer=make_layer({
            col_val_method: terms_col("Method", "method", col_val_count),
            col_val_count:   count_col(),
        }, [col_val_method, col_val_count], layer_val),
        visualization=pie_visualization(layer_val, col_val_method, col_val_count, shape="donut"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "value-manipulation"}}}],
    )

    # ── 18. Synthetic Events by Type (pie) ───────────────────────────────────
    layer_synth = uid(); col_synth_event = uid(); col_synth_count = uid()
    v_synth = lens_obj("v_synth", "Synthetic Events by Type", "lnsPie", layer_synth,
        layer=make_layer({
            col_synth_event: terms_col("Event Type", "event", col_synth_count),
            col_synth_count: count_col(),
        }, [col_synth_event, col_synth_count], layer_synth),
        visualization=pie_visualization(layer_synth, col_synth_event, col_synth_count, shape="donut"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"bool": {"must": [
                      {"term":  {"is_trusted": False}},
                  ]}}}],
    )

    # ── 19. Automation Alerts (pie) ──────────────────────────────────────────
    layer_auto_alert = uid(); col_auto_alert_event = uid(); col_auto_alert_count = uid()
    v_auto_alert = lens_obj("v_auto_alert", "Automation Alert Types", "lnsPie", layer_auto_alert,
        layer=make_layer({
            col_auto_alert_event: terms_col("Alert Type", "event", col_auto_alert_count),
            col_auto_alert_count: count_col(),
        }, [col_auto_alert_event, col_auto_alert_count], layer_auto_alert),
        visualization=pie_visualization(layer_auto_alert, col_auto_alert_event, col_auto_alert_count, shape="pie"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "automation-alert"}}}],
    )

    # ── 20. Form Submit Tracking (XY) ─────────────────────────────────────────
    layer_form = uid(); col_form_ts = uid(); col_form_count = uid()
    v_form = lens_obj("v_form", "Form Submissions Over Time", "lnsXY", layer_form,
        layer=make_layer({
            col_form_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_form_count: count_col(),
        }, [col_form_ts, col_form_count], layer_form),
        visualization=xy_visualization(layer_form, col_form_ts, col_form_count, series_type="bar"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "form-submit"}}}],
    )

    # ── 21. Form Submit Details (datatable) ─────────────────────────────────
    layer_form_detail = uid(); col_form_id = uid(); col_form_method = uid(); col_form_url = uid(); col_form_count_detail = uid()
    v_form_detail = lens_obj("v_form_detail", "Form Submissions Detail", "lnsDatatable", layer_form_detail,
        layer=make_layer({
            col_form_id:    terms_col_all("Form ID", "form_id", col_form_count_detail),
            col_form_method: terms_col("Method", "form_method", col_form_count_detail),
            col_form_url:  terms_col_all("URL", "url", col_form_count_detail),
            col_form_count_detail: count_col(),
        }, [col_form_id, col_form_method, col_form_url, col_form_count_detail], layer_form_detail),
        visualization=datatable_vis(layer_form_detail, [col_form_id, col_form_method, col_form_url, col_form_count_detail], col_form_count_detail),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "form-submit"}}}],
    )

    # ── 22. Clipboard Events (XY) ────────────────────────────────────────────
    layer_clip = uid(); col_clip_ts = uid(); col_clip_action = uid(); col_clip_count = uid()
    v_clip = lens_obj("v_clip", "Clipboard Actions Over Time", "lnsXY", layer_clip,
        layer=make_layer({
            col_clip_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_clip_action: terms_col("Action", "action", col_clip_count),
            col_clip_count: count_col(),
        }, [col_clip_ts, col_clip_action, col_clip_count], layer_clip),
        visualization=xy_visualization(layer_clip, col_clip_ts, col_clip_count, series_type="bar_stacked"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "clipboard"}}}],
    )

    # ── 23. Visibility Changes (XY) ─────────────────────────────────────────
    layer_vis = uid(); col_vis_ts = uid(); col_vis_state = uid(); col_vis_count = uid()
    v_vis = lens_obj("v_vis", "Page Visibility Changes", "lnsXY", layer_vis,
        layer=make_layer({
            col_vis_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_vis_state: terms_col("State", "state", col_vis_count),
            col_vis_count: count_col(),
        }, [col_vis_ts, col_vis_state, col_vis_count], layer_vis),
        visualization=xy_visualization(layer_vis, col_vis_ts, col_vis_count, series_type="bar_stacked"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "visibility"}}}],
    )

    # ── 24. Page Unload Tracking (XY) ────────────────────────────────────────
    layer_unload = uid(); col_unload_ts = uid(); col_unload_count = uid()
    v_unload = lens_obj("v_unload", "Page Unloads Over Time", "lnsXY", layer_unload,
        layer=make_layer({
            col_unload_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_unload_count: count_col(),
        }, [col_unload_ts, col_unload_count], layer_unload),
        visualization=xy_visualization(layer_unload, col_unload_ts, col_unload_count, series_type="area"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "page-unload"}}}],
    )

    # ── 25. Promise Rejection Tracking (XY) ─────────────────────────────────
    layer_promise = uid(); col_promise_ts = uid(); col_promise_count = uid()
    v_promise = lens_obj("v_promise", "Unhandled Promise Rejections Over Time", "lnsXY", layer_promise,
        layer=make_layer({
            col_promise_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_promise_count: count_col(),
        }, [col_promise_ts, col_promise_count], layer_promise),
        visualization=xy_visualization(layer_promise, col_promise_ts, col_promise_count, series_type="bar"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "promise-rejection"}}}],
    )

    # ── 26. Promise Rejection Details (datatable) ────────────────────────────
    layer_promise_detail = uid(); col_promise_msg = uid(); col_promise_url = uid(); col_promise_count_detail = uid()
    v_promise_detail = lens_obj("v_promise_detail", "Unhandled Promise Rejections Detail", "lnsDatatable", layer_promise_detail,
        layer=make_layer({
            col_promise_msg:   terms_col_all("Reason", "message.keyword", col_promise_count_detail),
            col_promise_url:   terms_col_all("URL", "url", col_promise_count_detail),
            col_promise_count_detail: count_col(),
        }, [col_promise_msg, col_promise_url, col_promise_count_detail], layer_promise_detail),
        visualization=datatable_vis(layer_promise_detail, [col_promise_msg, col_promise_url, col_promise_count_detail], col_promise_count_detail),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "promise-rejection"}}}],
    )

    # ── 27. User Interactions Over Time (XY) ───────────────────────────────
    layer_intr = uid(); col_intr_ts = uid(); col_intr_event = uid(); col_intr_count = uid()
    v_intr = lens_obj("v_intr", "User Interactions by Type", "lnsXY", layer_intr,
        layer=make_layer({
            col_intr_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_intr_event: terms_col("Event", "event", col_intr_count),
            col_intr_count: count_col(),
        }, [col_intr_ts, col_intr_event, col_intr_count], layer_intr),
        visualization=xy_visualization(layer_intr, col_intr_ts, col_intr_count, series_type="bar_stacked"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "interaction"}}}],
    )

    # ── 28. Session Analysis - Events per Session (datatable) ───────────────
    layer_sess = uid(); col_sess_id = uid(); col_sess_count = uid(); col_sess_url = uid()
    v_sess = lens_obj("v_sess", "Top Sessions by Event Count", "lnsDatatable", layer_sess,
        layer=make_layer({
            col_sess_id:   terms_col_all("Session ID", "session_id", col_sess_count),
            col_sess_url:  terms_col_all("URL", "url", col_sess_count),
            col_sess_count: count_col(),
        }, [col_sess_id, col_sess_url, col_sess_count], layer_sess),
        visualization=datatable_vis(layer_sess, [col_sess_id, col_sess_url, col_sess_count], col_sess_count),
    )

    # ── 29. Network Success vs Failure (pie) ─────────────────────────────────
    layer_net_status = uid(); col_net_success = uid(); col_net_status_count = uid()
    v_net_status = lens_obj("v_net_status", "Network Request Success Rate", "lnsPie", layer_net_status,
        layer=make_layer({
            col_net_success: {
                "dataType": "string",
                "isBucketed": True,
                "label": "Success",
                "operationType": "filters",
                "params": {
                    "filters": [
                        {"query": "success:true ", "label": "Successful"},
                        {"query": "success:false", "label": "Failed"},
                    ]
                },
                "sourceField": "success",
            },
            col_net_status_count: count_col(),
        }, [col_net_success, col_net_status_count], layer_net_status),
        visualization=pie_visualization(layer_net_status, col_net_success, col_net_status_count, shape="donut"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "network-request"}}}],
    )

    # ── 30. Top URLs by Activity (datatable) ─────────────────────────────────
    layer_urls = uid(); col_url = uid(); col_url_count = uid()
    v_urls = lens_obj("v_urls", "Top URLs by Event Count", "lnsDatatable", layer_urls,
        layer=make_layer({
            col_url:      terms_col_all("URL", "url", col_url_count),
            col_url_count: count_col(),
        }, [col_url, col_url_count], layer_urls),
        visualization=datatable_vis(layer_urls, [col_url, col_url_count], col_url_count),
    )

    # ── Dashboard ─────────────────────────────────────────────────────────────
    panels = [
        {"panelIndex": "1",  "type": "lens", "panelRefName": "panel_v_time",
         "gridData": {"x": 0,  "y": 0,  "w": 36, "h": 10, "i": "1"},  "embeddableConfig": {}},
        {"panelIndex": "2",  "type": "lens", "panelRefName": "panel_v_types",
         "gridData": {"x": 36, "y": 0, "w": 12, "h": 10, "i": "2"},  "embeddableConfig": {}},
        {"panelIndex": "3",  "type": "lens", "panelRefName": "panel_v_tags",
         "gridData": {"x": 48, "y": 0, "w": 12, "h": 10, "i": "3"},  "embeddableConfig": {}},
        
        {"panelIndex": "4",  "type": "lens", "panelRefName": "panel_v_failed_sel",
         "gridData": {"x": 0,  "y": 10, "w": 16, "h": 12, "i": "4"},  "embeddableConfig": {}},
        {"panelIndex": "5",  "type": "lens", "panelRefName": "panel_v_failed_xpath",
         "gridData": {"x": 16, "y": 10, "w": 16, "h": 12, "i": "5"},  "embeddableConfig": {}},
        {"panelIndex": "6",  "type": "lens", "panelRefName": "panel_v_js_err",
         "gridData": {"x": 32, "y": 10, "w": 16, "h": 12, "i": "6"},  "embeddableConfig": {}},
        {"panelIndex": "7",  "type": "lens", "panelRefName": "panel_v_perf",
         "gridData": {"x": 48, "y": 10, "w": 12, "h": 12, "i": "7"},  "embeddableConfig": {}},
        
        {"panelIndex": "8",  "type": "lens", "panelRefName": "panel_v_network",
         "gridData": {"x": 0,  "y": 22, "w": 12, "h": 10, "i": "8"},  "embeddableConfig": {}},
        {"panelIndex": "9",  "type": "lens", "panelRefName": "panel_v_net_status",
         "gridData": {"x": 12, "y": 22, "w": 12, "h": 10, "i": "9"},  "embeddableConfig": {}},
        {"panelIndex": "10", "type": "lens", "panelRefName": "panel_v_timing",
         "gridData": {"x": 24, "y": 22, "w": 12, "h": 10, "i": "10"}, "embeddableConfig": {}},
        {"panelIndex": "11", "type": "lens", "panelRefName": "panel_v_console",
         "gridData": {"x": 36, "y": 22, "w": 12, "h": 10, "i": "11"}, "embeddableConfig": {}},
        {"panelIndex": "12", "type": "lens", "panelRefName": "panel_v_conn",
         "gridData": {"x": 48, "y": 22, "w": 12, "h": 10, "i": "12"}, "embeddableConfig": {}},
        
        {"panelIndex": "13", "type": "lens", "panelRefName": "panel_v_auto",
         "gridData": {"x": 0,  "y": 32, "w": 8,  "h": 10, "i": "13"}, "embeddableConfig": {}},
        {"panelIndex": "14", "type": "lens", "panelRefName": "panel_v_synth",
         "gridData": {"x": 8,  "y": 32, "w": 8,  "h": 10, "i": "14"}, "embeddableConfig": {}},
        {"panelIndex": "15", "type": "lens", "panelRefName": "panel_v_auto_alert",
         "gridData": {"x": 16, "y": 32, "w": 8,  "h": 10, "i": "15"}, "embeddableConfig": {}},
        {"panelIndex": "16", "type": "lens", "panelRefName": "panel_v_elem",
         "gridData": {"x": 24, "y": 32, "w": 8,  "h": 10, "i": "16"}, "embeddableConfig": {}},
        {"panelIndex": "17", "type": "lens", "panelRefName": "panel_v_elem_act",
         "gridData": {"x": 32, "y": 32, "w": 8,  "h": 10, "i": "17"}, "embeddableConfig": {}},
        {"panelIndex": "18", "type": "lens", "panelRefName": "panel_v_val",
         "gridData": {"x": 40, "y": 32, "w": 8,  "h": 10, "i": "18"}, "embeddableConfig": {}},
        {"panelIndex": "19", "type": "lens", "panelRefName": "panel_v_data",
         "gridData": {"x": 48, "y": 32, "w": 12, "h": 10, "i": "19"}, "embeddableConfig": {}},
        
        {"panelIndex": "20", "type": "lens", "panelRefName": "panel_v_form",
         "gridData": {"x": 0,  "y": 42, "w": 12, "h": 10, "i": "20"}, "embeddableConfig": {}},
        {"panelIndex": "21", "type": "lens", "panelRefName": "panel_v_form_detail",
         "gridData": {"x": 12, "y": 42, "w": 24, "h": 10, "i": "21"}, "embeddableConfig": {}},
        {"panelIndex": "22", "type": "lens", "panelRefName": "panel_v_intr",
         "gridData": {"x": 36, "y": 42, "w": 24, "h": 10, "i": "22"}, "embeddableConfig": {}},
        
        {"panelIndex": "23", "type": "lens", "panelRefName": "panel_v_clip",
         "gridData": {"x": 0,  "y": 52, "w": 12, "h": 10, "i": "23"}, "embeddableConfig": {}},
        {"panelIndex": "24", "type": "lens", "panelRefName": "panel_v_vis",
         "gridData": {"x": 12, "y": 52, "w": 12, "h": 10, "i": "24"}, "embeddableConfig": {}},
        {"panelIndex": "25", "type": "lens", "panelRefName": "panel_v_unload",
         "gridData": {"x": 24, "y": 52, "w": 12, "h": 10, "i": "25"}, "embeddableConfig": {}},
        {"panelIndex": "26", "type": "lens", "panelRefName": "panel_v_promise",
         "gridData": {"x": 36, "y": 52, "w": 12, "h": 10, "i": "26"}, "embeddableConfig": {}},
        
        {"panelIndex": "27", "type": "lens", "panelRefName": "panel_v_mut",
         "gridData": {"x": 48, "y": 52, "w": 12, "h": 10, "i": "27"}, "embeddableConfig": {}},
        
        {"panelIndex": "28", "type": "lens", "panelRefName": "panel_v_sess",
         "gridData": {"x": 0,  "y": 62, "w": 30, "h": 12, "i": "28"}, "embeddableConfig": {}},
        {"panelIndex": "29", "type": "lens", "panelRefName": "panel_v_urls",
         "gridData": {"x": 30, "y": 62, "w": 30, "h": 12, "i": "29"}, "embeddableConfig": {}},
        
        {"panelIndex": "30", "type": "lens", "panelRefName": "panel_v_promise_detail",
         "gridData": {"x": 0,  "y": 74, "w": 60, "h": 12, "i": "30"}, "embeddableConfig": {}},
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
            {"name": "panel_v_net_status",   "type": "lens", "id": "v_net_status"},
            {"name": "panel_v_timing",       "type": "lens", "id": "v_timing"},
            {"name": "panel_v_console",      "type": "lens", "id": "v_console"},
            {"name": "panel_v_conn",         "type": "lens", "id": "v_conn"},
            {"name": "panel_v_elem",         "type": "lens", "id": "v_elem"},
            {"name": "panel_v_elem_act",     "type": "lens", "id": "v_elem_act"},
            {"name": "panel_v_auto",         "type": "lens", "id": "v_auto"},
            {"name": "panel_v_mut",          "type": "lens", "id": "v_mut"},
            {"name": "panel_v_data",         "type": "lens", "id": "v_data"},
            {"name": "panel_v_val",          "type": "lens", "id": "v_val"},
            {"name": "panel_v_synth",        "type": "lens", "id": "v_synth"},
            {"name": "panel_v_auto_alert",   "type": "lens", "id": "v_auto_alert"},
            {"name": "panel_v_form",         "type": "lens", "id": "v_form"},
            {"name": "panel_v_form_detail",  "type": "lens", "id": "v_form_detail"},
            {"name": "panel_v_clip",         "type": "lens", "id": "v_clip"},
            {"name": "panel_v_vis",          "type": "lens", "id": "v_vis"},
            {"name": "panel_v_unload",       "type": "lens", "id": "v_unload"},
            {"name": "panel_v_promise",      "type": "lens", "id": "v_promise"},
            {"name": "panel_v_promise_detail", "type": "lens", "id": "v_promise_detail"},
            {"name": "panel_v_intr",         "type": "lens", "id": "v_intr"},
            {"name": "panel_v_sess",         "type": "lens", "id": "v_sess"},
            {"name": "panel_v_urls",         "type": "lens", "id": "v_urls"},
        ],
        "coreMigrationVersion": "8.8.0",
    }

    objects = [v_time, v_types, v_failed_sel, v_failed_xpath, v_js_err, v_tags,
               v_perf, v_network, v_net_status, v_timing, v_console, v_conn, v_elem, v_elem_act,
               v_auto, v_mut, v_data, v_val, v_synth, v_auto_alert, v_form, v_form_detail,
               v_clip, v_vis, v_unload, v_promise, v_promise_detail, v_intr, v_sess, v_urls, dashboard]
    return "\n".join(json.dumps(obj) for obj in objects)


# ─────────────────────────────────────────────────────────────────────────────
# V2: Operations Error & Sources Dashboard
# ─────────────────────────────────────────────────────────────────────────────
DASHBOARD_ID_V2 = "operations-error-sources-dashboard"
DATA_VIEW_ID_V2 = "selenium-events-ops-view"


def get_or_create_data_view_v2() -> str:
    logger.info(f"[Kibana] Creating data view v2: {INDEX_PATTERN}")
    payload = {
        "data_view": {
            "id":            DATA_VIEW_ID_V2,
            "title":         INDEX_PATTERN,
            "name":          "Selenium Events Ops View",
            "timeFieldName": "@timestamp",
        },
        "override": True,
    }
    res = json_session.post(f"{KIBANA_URL}/api/data_views/data_view", json=payload)
    if res.status_code in (200, 201):
        dv_id = res.json()["data_view"]["id"]
        logger.info(f"[Kibana] Data view v2 created: {dv_id}")
        return dv_id

    if res.status_code == 400 and "already exists" in res.text:
        logger.info("[Kibana] Data view v2 already exists, searching...")
    else:
        logger.warning(f"[Kibana] Failed to create data view v2 ({res.status_code}): {res.text}")

    get_res = json_session.get(f"{KIBANA_URL}/api/data_views")
    if get_res.status_code == 200:
        for dv in get_res.json().get("data_view", []):
            if dv.get("title") == INDEX_PATTERN:
                dv_id = dv["id"]
                logger.info(f"[Kibana] Found existing data view v2: {dv_id}")
                return dv_id

    logger.warning("[Kibana] Using default data view ID")
    return DATA_VIEW_ID_V2


def build_ndjson_v2(dv_id: str) -> str:

    def uid():
        return str(uuid.uuid4())

    def make_layer(columns: dict, column_order: list, layer_id: str) -> dict:
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

    def terms_col_all(label, field, order_col, size=10000):
        return {
            "dataType":      "string",
            "isBucketed":    True,
            "label":         label,
            "operationType": "terms",
            "params": {
                "size":           size,
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

    def lens_obj(vis_id, title, vis_type, layer_id, layer, visualization, filters=None):
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

    # ── Metrics Row: Using datatables with single row ─────────────────────────
    layer_metric1 = uid(); col_m1 = uid()
    v_total_events = lens_obj("v_total_events", "Total Events", "lnsDatatable", layer_metric1,
        layer=make_layer({col_m1: count_col()}, [col_m1], layer_metric1),
        visualization=datatable_vis(layer_metric1, [col_m1], col_m1),
    )

    layer_metric2 = uid(); col_m2 = uid()
    error_filter = [{"meta": {"type": "custom", "disabled": False, "negate": False},
                    "query": {"bool": {"should": [
                        {"match": {"type": "js-error"}},
                        {"match": {"type": "promise-rejection"}},
                        {"match": {"type": "console-error"}},
                        {"term": {"found": False}},
                    ], "minimum_should_match": 1}}}]
    v_error_count = lens_obj("v_error_count", "Error Events", "lnsDatatable", layer_metric2,
        layer=make_layer({col_m2: count_col()}, [col_m2], layer_metric2),
        visualization=datatable_vis(layer_metric2, [col_m2], col_m2),
        filters=error_filter,
    )

    layer_metric3 = uid(); col_m3 = uid()
    v_unique_sessions = lens_obj("v_unique_sessions", "Unique Sessions", "lnsDatatable", layer_metric3,
        layer=make_layer({col_m3: {
            "dataType": "number", "isBucketed": False,
            "label": "Count", "operationType": "unique_count",
            "params": {"emptyAsNull": True}, "sourceField": "session_id",
        }}, [col_m3], layer_metric3),
        visualization=datatable_vis(layer_metric3, [col_m3], col_m3),
    )

    layer_metric4 = uid(); col_m4 = uid()
    v_unique_urls = lens_obj("v_unique_urls", "Unique URLs", "lnsDatatable", layer_metric4,
        layer=make_layer({col_m4: {
            "dataType": "number", "isBucketed": False,
            "label": "Count", "operationType": "unique_count",
            "params": {"emptyAsNull": True}, "sourceField": "url",
        }}, [col_m4], layer_metric4),
        visualization=datatable_vis(layer_metric4, [col_m4], col_m4),
    )

    # ── Sources: Top URLs ────────────────────────────────────────────────────
    layer_urls = uid(); col_url = uid(); col_url_count = uid()
    v_top_urls = lens_obj("v_top_urls", "Top URLs by Event Count", "lnsDatatable", layer_urls,
        layer=make_layer({
            col_url:       terms_col_all("URL", "url", col_url_count),
            col_url_count: count_col(),
        }, [col_url, col_url_count], layer_urls),
        visualization=datatable_vis(layer_urls, [col_url, col_url_count], col_url_count),
    )

    # ── Sources: Top User Agents ────────────────────────────────────────────
    layer_ua = uid(); col_ua = uid(); col_ua_count = uid()
    v_top_ua = lens_obj("v_top_ua", "Top User Agents", "lnsDatatable", layer_ua,
        layer=make_layer({
            col_ua:       terms_col_all("User Agent", "user_agent.keyword", col_ua_count),
            col_ua_count: count_col(),
        }, [col_ua, col_ua_count], layer_ua),
        visualization=datatable_vis(layer_ua, [col_ua, col_ua_count], col_ua_count),
    )

    # ── Sources: Events by Session Over Time ────────────────────────────────
    layer_sess_ts = uid(); col_sess_ts = uid(); col_sess_count = uid()
    v_sess_ts = lens_obj("v_sess_ts", "Unique Sessions Over Time", "lnsXY", layer_sess_ts,
        layer=make_layer({
            col_sess_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_sess_count: {
                "dataType": "number", "isBucketed": False,
                "label": "Unique Sessions", "operationType": "unique_count",
                "params": {"emptyAsNull": True}, "sourceField": "session_id",
            },
        }, [col_sess_ts, col_sess_count], layer_sess_ts),
        visualization=xy_visualization(layer_sess_ts, col_sess_ts, col_sess_count, series_type="area"),
    )

    # ── Sources: Top Referrer URLs ───────────────────────────────────────────
    layer_ref = uid(); col_ref = uid(); col_ref_count = uid()
    v_top_ref = lens_obj("v_top_ref", "Top Referrer URLs", "lnsDatatable", layer_ref,
        layer=make_layer({
            col_ref:       terms_col_all("Referrer", "referrer", col_ref_count),
            col_ref_count: count_col(),
        }, [col_ref, col_ref_count], layer_ref),
        visualization=datatable_vis(layer_ref, [col_ref, col_ref_count], col_ref_count),
    )

    # ── Query Failures: Failed Selectors Over Time ─────────────────────────
    layer_fail_sel_ts = uid(); col_fail_sel_ts = uid(); col_fail_sel_count = uid()
    v_fail_sel_ts = lens_obj("v_fail_sel_ts", "Failed Selectors Over Time", "lnsXY", layer_fail_sel_ts,
        layer=make_layer({
            col_fail_sel_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_fail_sel_count: count_col(),
        }, [col_fail_sel_ts, col_fail_sel_count], layer_fail_sel_ts),
        visualization=xy_visualization(layer_fail_sel_ts, col_fail_sel_ts, col_fail_sel_count, series_type="bar"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"bool": {"must": [
                      {"term":  {"found": False}},
                      {"match": {"type": "dom-query"}},
                  ]}}}],
    )

    # ── Query Failures: Failed XPaths Over Time ─────────────────────────────
    layer_fail_xpath_ts = uid(); col_fail_xpath_ts = uid(); col_fail_xpath_count = uid()
    v_fail_xpath_ts = lens_obj("v_fail_xpath_ts", "Failed XPaths Over Time", "lnsXY", layer_fail_xpath_ts,
        layer=make_layer({
            col_fail_xpath_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_fail_xpath_count: count_col(),
        }, [col_fail_xpath_ts, col_fail_xpath_count], layer_fail_xpath_ts),
        visualization=xy_visualization(layer_fail_xpath_ts, col_fail_xpath_ts, col_fail_xpath_count, series_type="bar"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"bool": {"must": [
                      {"term":  {"found": False}},
                      {"match": {"type": "xpath-query"}},
                  ]}}}],
    )

    # ── Query Failures: Failed Selectors Detail ─────────────────────────────
    layer_fail_sel_detail = uid(); col_fail_sel = uid(); col_fail_sel_url = uid(); col_fail_sel_count_d = uid()
    v_fail_sel_detail = lens_obj("v_fail_sel_detail", "Failed Selectors Detail", "lnsDatatable", layer_fail_sel_detail,
        layer=make_layer({
            col_fail_sel:       terms_col_all("Selector", "selector", col_fail_sel_count_d),
            col_fail_sel_url:   terms_col_all("URL", "url", col_fail_sel_count_d),
            col_fail_sel_count_d: count_col(),
        }, [col_fail_sel, col_fail_sel_url, col_fail_sel_count_d], layer_fail_sel_detail),
        visualization=datatable_vis(layer_fail_sel_detail, [col_fail_sel, col_fail_sel_url, col_fail_sel_count_d], col_fail_sel_count_d),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"bool": {"must": [
                      {"term":  {"found": False}},
                      {"match": {"type": "dom-query"}},
                  ]}}}],
    )

    # ── Query Failures: Failed XPaths Detail ────────────────────────────────
    layer_fail_xpath_detail = uid(); col_fail_xpath = uid(); col_fail_xpath_url = uid(); col_fail_xpath_count_d = uid()
    v_fail_xpath_detail = lens_obj("v_fail_xpath_detail", "Failed XPaths Detail", "lnsDatatable", layer_fail_xpath_detail,
        layer=make_layer({
            col_fail_xpath:       terms_col_all("XPath", "xpath", col_fail_xpath_count_d),
            col_fail_xpath_url:   terms_col_all("URL", "url", col_fail_xpath_count_d),
            col_fail_xpath_count_d: count_col(),
        }, [col_fail_xpath, col_fail_xpath_url, col_fail_xpath_count_d], layer_fail_xpath_detail),
        visualization=datatable_vis(layer_fail_xpath_detail, [col_fail_xpath, col_fail_xpath_url, col_fail_xpath_count_d], col_fail_xpath_count_d),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"bool": {"must": [
                      {"term":  {"found": False}},
                      {"match": {"type": "xpath-query"}},
                  ]}}}],
    )

    # ── Network: Success vs Failure Rate (pie) ───────────────────────────────
    layer_net_rate = uid(); col_net_success = uid(); col_net_count = uid()
    v_net_rate = lens_obj("v_net_rate", "Network Success vs Failure Rate", "lnsPie", layer_net_rate,
        layer=make_layer({
            col_net_success: {
                "dataType": "string",
                "isBucketed": True,
                "label": "Status",
                "operationType": "filters",
                "params": {
                    "filters": [
                        {"query": "success:true ", "label": "Successful"},
                        {"query": "success:false", "label": "Failed"},
                    ]
                },
                "sourceField": "success",
            },
            col_net_count: count_col(),
        }, [col_net_success, col_net_count], layer_net_rate),
        visualization=pie_visualization(layer_net_rate, col_net_success, col_net_count, shape="donut"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "network-request"}}}],
    )

    # ── Network: Failed Requests Detail ─────────────────────────────────────
    layer_net_fail = uid(); col_net_fail_url = uid(); col_net_fail_method = uid(); col_net_fail_status = uid(); col_net_fail_count = uid()
    v_net_fail = lens_obj("v_net_fail", "Failed Network Requests", "lnsDatatable", layer_net_fail,
        layer=make_layer({
            col_net_fail_url:    terms_col_all("URL", "request_url", col_net_fail_count),
            col_net_fail_method: terms_col("Method", "request_method", col_net_fail_count),
            col_net_fail_status: terms_col("Status", "status_code", col_net_fail_count),
            col_net_fail_count:  count_col(),
        }, [col_net_fail_url, col_net_fail_method, col_net_fail_status, col_net_fail_count], layer_net_fail),
        visualization=datatable_vis(layer_net_fail, [col_net_fail_url, col_net_fail_method, col_net_fail_status, col_net_fail_count], col_net_fail_count),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"bool": {"must": [
                      {"match": {"type": "network-request"}},
                      {"term": {"success": False}},
                  ]}}}],
    )

    # ── Network: Response Time Distribution ────────────────────────────────
    layer_net_time = uid(); col_net_time_url = uid(); col_net_time_avg = uid(); col_net_time_count = uid()
    v_net_time = lens_obj("v_net_time", "Network Response Times by URL", "lnsDatatable", layer_net_time,
        layer=make_layer({
            col_net_time_url:   terms_col_all("URL", "request_url", col_net_time_count),
            col_net_time_avg: {
                "dataType": "number", "isBucketed": False,
                "label": "Avg Duration (ms)", "operationType": "average",
                "params": {"emptyAsNull": True}, "sourceField": "duration_ms",
            },
            col_net_time_count: count_col(),
        }, [col_net_time_url, col_net_time_avg, col_net_time_count], layer_net_time),
        visualization=datatable_vis(layer_net_time, [col_net_time_url, col_net_time_avg, col_net_time_count], col_net_time_avg),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "network-request"}}}],
    )

    # ── JS Errors: Over Time ────────────────────────────────────────────────
    layer_js_ts = uid(); col_js_ts = uid(); col_js_count = uid()
    v_js_ts = lens_obj("v_js_ts", "JavaScript Errors Over Time", "lnsXY", layer_js_ts,
        layer=make_layer({
            col_js_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_js_count: count_col(),
        }, [col_js_ts, col_js_count], layer_js_ts),
        visualization=xy_visualization(layer_js_ts, col_js_ts, col_js_count, series_type="bar"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "js-error"}}}],
    )

    # ── JS Errors: Detail ───────────────────────────────────────────────────
    layer_js_detail = uid(); col_js_msg = uid(); col_js_source = uid(); col_js_url = uid(); col_js_lineno = uid(); col_js_count_d = uid()
    v_js_detail = lens_obj("v_js_detail", "JavaScript Errors Detail", "lnsDatatable", layer_js_detail,
        layer=make_layer({
            col_js_msg:    terms_col_all("Message", "message.keyword", col_js_count_d),
            col_js_source: terms_col_all("Source", "source", col_js_count_d),
            col_js_url:    terms_col_all("URL", "url", col_js_count_d),
            col_js_lineno: {
                "dataType": "number", "isBucketed": False,
                "label": "Line No", "operationType": "median",
                "params": {"emptyAsNull": True}, "sourceField": "lineno",
            },
            col_js_count_d: count_col(),
        }, [col_js_msg, col_js_source, col_js_url, col_js_lineno, col_js_count_d], layer_js_detail),
        visualization=datatable_vis(layer_js_detail, [col_js_msg, col_js_source, col_js_url, col_js_lineno, col_js_count_d], col_js_count_d),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "js-error"}}}],
    )

    # ── Promise Rejections: Over Time ──────────────────────────────────────
    layer_promise_ts = uid(); col_promise_ts = uid(); col_promise_count = uid()
    v_promise_ts = lens_obj("v_promise_ts", "Unhandled Promise Rejections Over Time", "lnsXY", layer_promise_ts,
        layer=make_layer({
            col_promise_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_promise_count: count_col(),
        }, [col_promise_ts, col_promise_count], layer_promise_ts),
        visualization=xy_visualization(layer_promise_ts, col_promise_ts, col_promise_count, series_type="bar"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "promise-rejection"}}}],
    )

    # ── Promise Rejections: Detail ─────────────────────────────────────────
    layer_promise_detail = uid(); col_promise_msg = uid(); col_promise_url = uid(); col_promise_count_d = uid()
    v_promise_detail = lens_obj("v_promise_detail", "Unhandled Promise Rejections Detail", "lnsDatatable", layer_promise_detail,
        layer=make_layer({
            col_promise_msg:    terms_col_all("Reason", "message.keyword", col_promise_count_d),
            col_promise_url:    terms_col_all("URL", "url", col_promise_count_d),
            col_promise_count_d: count_col(),
        }, [col_promise_msg, col_promise_url, col_promise_count_d], layer_promise_detail),
        visualization=datatable_vis(layer_promise_detail, [col_promise_msg, col_promise_url, col_promise_count_d], col_promise_count_d),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "promise-rejection"}}}],
    )

    # ── Console Errors & Warnings ───────────────────────────────────────────
    layer_console = uid(); col_console_msg = uid(); col_console_level = uid(); col_console_count = uid()
    v_console = lens_obj("v_console_ops", "Console Errors & Warnings", "lnsDatatable", layer_console,
        layer=make_layer({
            col_console_msg:   terms_col_all("Message", "message.keyword", col_console_count),
            col_console_level: terms_col("Level", "level", col_console_count),
            col_console_count: count_col(),
        }, [col_console_msg, col_console_level, col_console_count], layer_console),
        visualization=datatable_vis(layer_console, [col_console_msg, col_console_level, col_console_count], col_console_count),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "console-error"}}}],
    )

    # ── Console: Over Time ─────────────────────────────────────────────────
    layer_console_ts = uid(); col_console_ts = uid(); col_console_count_ts = uid()
    v_console_ts = lens_obj("v_console_ts", "Console Errors Over Time", "lnsXY", layer_console_ts,
        layer=make_layer({
            col_console_ts: {
                "dataType": "date", "isBucketed": True,
                "label": "@timestamp", "operationType": "date_histogram",
                "params": {"dropPartials": False, "includeEmptyRows": True, "interval": "auto"},
                "sourceField": "@timestamp",
            },
            col_console_count_ts: count_col(),
        }, [col_console_ts, col_console_count_ts], layer_console_ts),
        visualization=xy_visualization(layer_console_ts, col_console_ts, col_console_count_ts, series_type="bar"),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "console-error"}}}],
    )

    # ── Critical: Automation Detected Count ────────────────────────────────
    layer_metric_auto = uid(); col_ma = uid()
    v_auto_count = lens_obj("v_auto_count", "Automation Detected", "lnsDatatable", layer_metric_auto,
        layer=make_layer({col_ma: count_col()}, [col_ma], layer_metric_auto),
        visualization=datatable_vis(layer_metric_auto, [col_ma], col_ma),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "automation-detected"}}}],
    )

    # ── Critical: Timing Alerts Count ──────────────────────────────────────
    layer_metric_timing = uid(); col_mt = uid()
    v_timing_count = lens_obj("v_timing_count", "Timing Alerts", "lnsDatatable", layer_metric_timing,
        layer=make_layer({col_mt: count_col()}, [col_mt], layer_metric_timing),
        visualization=datatable_vis(layer_metric_timing, [col_mt], col_mt),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "timing-alert"}}}],
    )

    # ── Critical: Value Manipulation Count ──────────────────────────────────
    layer_metric_val = uid(); col_mv = uid()
    v_val_count = lens_obj("v_val_count", "Value Manipulation", "lnsDatatable", layer_metric_val,
        layer=make_layer({col_mv: count_col()}, [col_mv], layer_metric_val),
        visualization=datatable_vis(layer_metric_val, [col_mv], col_mv),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"match": {"type": "value-manipulation"}}}],
    )

    # ── Critical: Synthetic Events Count ────────────────────────────────────
    layer_metric_synth = uid(); col_ms = uid()
    v_synth_count = lens_obj("v_synth_count", "Synthetic Events", "lnsDatatable", layer_metric_synth,
        layer=make_layer({col_ms: count_col()}, [col_ms], layer_metric_synth),
        visualization=datatable_vis(layer_metric_synth, [col_ms], col_ms),
        filters=[{"meta": {"type": "custom", "disabled": False, "negate": False},
                  "query": {"term": {"is_trusted": False}}}],
    )

    # ── Dashboard ─────────────────────────────────────────────────────────
    panels = [
        {"panelIndex": "1",  "type": "lens", "panelRefName": "panel_v_total_events",
         "gridData": {"x": 0,  "y": 0,  "w": 6,  "h": 6,  "i": "1"},  "embeddableConfig": {}},
        {"panelIndex": "2",  "type": "lens", "panelRefName": "panel_v_error_count",
         "gridData": {"x": 6,  "y": 0,  "w": 6,  "h": 6,  "i": "2"},  "embeddableConfig": {}},
        {"panelIndex": "3",  "type": "lens", "panelRefName": "panel_v_unique_sessions",
         "gridData": {"x": 12, "y": 0,  "w": 6,  "h": 6,  "i": "3"},  "embeddableConfig": {}},
        {"panelIndex": "4",  "type": "lens", "panelRefName": "panel_v_unique_urls",
         "gridData": {"x": 18, "y": 0,  "w": 6,  "h": 6,  "i": "4"},  "embeddableConfig": {}},
        
        {"panelIndex": "5",  "type": "lens", "panelRefName": "panel_v_auto_count",
         "gridData": {"x": 24, "y": 0,  "w": 6,  "h": 6,  "i": "5"},  "embeddableConfig": {}},
        {"panelIndex": "6",  "type": "lens", "panelRefName": "panel_v_timing_count",
         "gridData": {"x": 30, "y": 0,  "w": 6,  "h": 6,  "i": "6"},  "embeddableConfig": {}},
        {"panelIndex": "7",  "type": "lens", "panelRefName": "panel_v_val_count",
         "gridData": {"x": 36, "y": 0,  "w": 6,  "h": 6,  "i": "7"},  "embeddableConfig": {}},
        {"panelIndex": "8",  "type": "lens", "panelRefName": "panel_v_synth_count",
         "gridData": {"x": 42, "y": 0,  "w": 6,  "h": 6,  "i": "8"},  "embeddableConfig": {}},
        
        {"panelIndex": "9",  "type": "lens", "panelRefName": "panel_v_top_urls",
         "gridData": {"x": 0,  "y": 6,  "w": 24, "h": 10, "i": "9"},  "embeddableConfig": {}},
        {"panelIndex": "10", "type": "lens", "panelRefName": "panel_v_top_ua",
         "gridData": {"x": 24, "y": 6,  "w": 24, "h": 10, "i": "10"}, "embeddableConfig": {}},
        
        {"panelIndex": "11", "type": "lens", "panelRefName": "panel_v_sess_ts",
         "gridData": {"x": 0,  "y": 16, "w": 24, "h": 10, "i": "11"}, "embeddableConfig": {}},
        {"panelIndex": "12", "type": "lens", "panelRefName": "panel_v_top_ref",
         "gridData": {"x": 24, "y": 16, "w": 24, "h": 10, "i": "12"}, "embeddableConfig": {}},
        
        {"panelIndex": "13", "type": "lens", "panelRefName": "panel_v_fail_sel_ts",
         "gridData": {"x": 0,  "y": 26, "w": 24, "h": 10, "i": "13"}, "embeddableConfig": {}},
        {"panelIndex": "14", "type": "lens", "panelRefName": "panel_v_fail_xpath_ts",
         "gridData": {"x": 24, "y": 26, "w": 24, "h": 10, "i": "14"}, "embeddableConfig": {}},
        
        {"panelIndex": "15", "type": "lens", "panelRefName": "panel_v_fail_sel_detail",
         "gridData": {"x": 0,  "y": 36, "w": 24, "h": 12, "i": "15"}, "embeddableConfig": {}},
        {"panelIndex": "16", "type": "lens", "panelRefName": "panel_v_fail_xpath_detail",
         "gridData": {"x": 24, "y": 36, "w": 24, "h": 12, "i": "16"}, "embeddableConfig": {}},
        
        {"panelIndex": "17", "type": "lens", "panelRefName": "panel_v_net_rate",
         "gridData": {"x": 0,  "y": 48, "w": 12, "h": 10, "i": "17"}, "embeddableConfig": {}},
        {"panelIndex": "18", "type": "lens", "panelRefName": "panel_v_net_fail",
         "gridData": {"x": 12, "y": 48, "w": 18, "h": 10, "i": "18"}, "embeddableConfig": {}},
        {"panelIndex": "19", "type": "lens", "panelRefName": "panel_v_net_time",
         "gridData": {"x": 30, "y": 48, "w": 18, "h": 10, "i": "19"}, "embeddableConfig": {}},
        
        {"panelIndex": "20", "type": "lens", "panelRefName": "panel_v_js_ts",
         "gridData": {"x": 0,  "y": 58, "w": 24, "h": 10, "i": "20"}, "embeddableConfig": {}},
        {"panelIndex": "21", "type": "lens", "panelRefName": "panel_v_js_detail",
         "gridData": {"x": 24, "y": 58, "w": 24, "h": 10, "i": "21"}, "embeddableConfig": {}},
        
        {"panelIndex": "22", "type": "lens", "panelRefName": "panel_v_promise_ts",
         "gridData": {"x": 0,  "y": 68, "w": 24, "h": 10, "i": "22"}, "embeddableConfig": {}},
        {"panelIndex": "23", "type": "lens", "panelRefName": "panel_v_promise_detail",
         "gridData": {"x": 24, "y": 68, "w": 24, "h": 10, "i": "23"}, "embeddableConfig": {}},
        
        {"panelIndex": "24", "type": "lens", "panelRefName": "panel_v_console_ts",
         "gridData": {"x": 0,  "y": 78, "w": 24, "h": 10, "i": "24"}, "embeddableConfig": {}},
        {"panelIndex": "25", "type": "lens", "panelRefName": "panel_v_console",
         "gridData": {"x": 24, "y": 78, "w": 24, "h": 10, "i": "25"}, "embeddableConfig": {}},
    ]

    dashboard_v2 = {
        "type":    "dashboard",
        "id":      DASHBOARD_ID_V2,
        "managed": False,
        "attributes": {
            "title":       "Operations: Error & Sources Dashboard",
            "description": "Error tracking, query failures, network issues, and event sources analysis",
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
            {"name": "panel_v_total_events",     "type": "lens", "id": "v_total_events"},
            {"name": "panel_v_error_count",      "type": "lens", "id": "v_error_count"},
            {"name": "panel_v_unique_sessions",  "type": "lens", "id": "v_unique_sessions"},
            {"name": "panel_v_unique_urls",      "type": "lens", "id": "v_unique_urls"},
            {"name": "panel_v_auto_count",       "type": "lens", "id": "v_auto_count"},
            {"name": "panel_v_timing_count",     "type": "lens", "id": "v_timing_count"},
            {"name": "panel_v_val_count",        "type": "lens", "id": "v_val_count"},
            {"name": "panel_v_synth_count",      "type": "lens", "id": "v_synth_count"},
            {"name": "panel_v_top_urls",         "type": "lens", "id": "v_top_urls"},
            {"name": "panel_v_top_ua",           "type": "lens", "id": "v_top_ua"},
            {"name": "panel_v_sess_ts",          "type": "lens", "id": "v_sess_ts"},
            {"name": "panel_v_top_ref",          "type": "lens", "id": "v_top_ref"},
            {"name": "panel_v_fail_sel_ts",     "type": "lens", "id": "v_fail_sel_ts"},
            {"name": "panel_v_fail_xpath_ts",   "type": "lens", "id": "v_fail_xpath_ts"},
            {"name": "panel_v_fail_sel_detail",  "type": "lens", "id": "v_fail_sel_detail"},
            {"name": "panel_v_fail_xpath_detail", "type": "lens", "id": "v_fail_xpath_detail"},
            {"name": "panel_v_net_rate",         "type": "lens", "id": "v_net_rate"},
            {"name": "panel_v_net_fail",        "type": "lens", "id": "v_net_fail"},
            {"name": "panel_v_net_time",        "type": "lens", "id": "v_net_time"},
            {"name": "panel_v_js_ts",           "type": "lens", "id": "v_js_ts"},
            {"name": "panel_v_js_detail",       "type": "lens", "id": "v_js_detail"},
            {"name": "panel_v_promise_ts",      "type": "lens", "id": "v_promise_ts"},
            {"name": "panel_v_promise_detail",  "type": "lens", "id": "v_promise_detail"},
            {"name": "panel_v_console_ts",       "type": "lens", "id": "v_console_ts"},
            {"name": "panel_v_console",          "type": "lens", "id": "v_console_ops"},
        ],
        "coreMigrationVersion": "8.8.0",
    }

    objects = [
        v_total_events, v_error_count, v_unique_sessions, v_unique_urls,
        v_auto_count, v_timing_count, v_val_count, v_synth_count,
        v_top_urls, v_top_ua, v_sess_ts, v_top_ref,
        v_fail_sel_ts, v_fail_xpath_ts, v_fail_sel_detail, v_fail_xpath_detail,
        v_net_rate, v_net_fail, v_net_time,
        v_js_ts, v_js_detail, v_promise_ts, v_promise_detail,
        v_console_ts, v_console, dashboard_v2
    ]
    return "\n".join(json.dumps(obj) for obj in objects)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
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
    
    # Build main comprehensive dashboard
    dv_id = get_or_create_data_view()
    ndjson = build_ndjson(dv_id)
    import_saved_objects(ndjson)
    logger.info(f"[Kibana] Dashboard ready -> {KIBANA_URL}/app/dashboards#/view/{DASHBOARD_ID}")
    
    # Build operations error & sources dashboard
    dv_id_v2 = get_or_create_data_view_v2()
    ndjson_v2 = build_ndjson_v2(dv_id_v2)
    import_saved_objects(ndjson_v2)
    logger.info(f"[Kibana] Operations Dashboard ready -> {KIBANA_URL}/app/dashboards#/view/{DASHBOARD_ID_V2}")


if __name__ == "__main__":
    configure_kibana_system()
    build_dashboard()

    while True:
        time.sleep(60)