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
DATA_VIEW_ID  = "selenium-events-data-view"

session = requests.Session()
session.headers.update({"kbn-xsrf": "true"})
session.auth = (ELASTIC_USERNAME, ELASTIC_PASSWORD)

json_session = requests.Session()
json_session.headers.update({"kbn-xsrf": "true", "Content-Type": "application/json"})
json_session.auth = (ELASTIC_USERNAME, ELASTIC_PASSWORD)


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap helpers
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


def mark_elastic_ready():
    with open("/tmp/elastic_ready", "w") as f:
        f.write("ok")


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

    logger.warning("[Kibana] Using default data view ID")
    return DATA_VIEW_ID


# ─────────────────────────────────────────────────────────────────────────────
# Delete existing dashboards / visualizations before re-deploy
# ─────────────────────────────────────────────────────────────────────────────

def delete_existing_saved_objects():
    """Remove all existing dashboards and lens visualizations so we start clean."""
    for obj_type in ("dashboard", "lens"):
        logger.info(f"[Kibana] Searching for existing {obj_type} objects...")
        try:
            res = json_session.get(
                f"{KIBANA_URL}/api/saved_objects/_find",
                params={"type": obj_type, "per_page": 1000}
            )
            if res.status_code != 200:
                logger.warning(f"[Kibana] Could not list {obj_type}: {res.status_code}")
                continue

            items = res.json().get("saved_objects", [])
            logger.info(f"[Kibana] Found {len(items)} {obj_type}(s) to delete")
            for item in items:
                obj_id = item["id"]
                del_res = json_session.delete(
                    f"{KIBANA_URL}/api/saved_objects/{obj_type}/{obj_id}",
                    params={"force": "true"}
                )
                if del_res.status_code in (200, 204):
                    logger.info(f"[Kibana]  ✓ Deleted {obj_type}/{obj_id}")
                else:
                    logger.warning(f"[Kibana]  ✗ Failed to delete {obj_type}/{obj_id}: {del_res.status_code}")
        except Exception as e:
            logger.warning(f"[Kibana] Error during {obj_type} deletion: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Lens column helpers
# ─────────────────────────────────────────────────────────────────────────────

def uid():
    return str(uuid.uuid4())


def make_layer(columns: dict, column_order: list, layer_id: str) -> dict:
    return {
        "columnOrder": column_order,
        "columns": columns,
        "incompleteColumns": {},
        "sampling": 1,
    }


def count_col(label="Count"):
    return {
        "dataType": "number",
        "isBucketed": False,
        "label": label,
        "operationType": "count",
        "params": {"emptyAsNull": False},
        "sourceField": "___records___",
    }


def terms_col(label, field, order_col_id, size=10, missing_bucket=False):
    return {
        "dataType": "string",
        "isBucketed": True,
        "label": label,
        "operationType": "terms",
        "params": {
            "size": size,
            "orderBy": {"type": "column", "columnId": order_col_id},
            "orderDirection": "desc",
            "otherBucket": True,
            "missingBucket": missing_bucket,
            "parentFormat": {"id": "terms"},
        },
        "sourceField": field,
    }


def terms_col_all(label, field, order_col_id, size=10000, missing_bucket=False):
    return {
        "dataType": "string",
        "isBucketed": True,
        "label": label,
        "operationType": "terms",
        "params": {
            "size": size,
            "orderBy": {"type": "column", "columnId": order_col_id},
            "orderDirection": "desc",
            "otherBucket": False,
            "missingBucket": missing_bucket,
            "parentFormat": {"id": "terms"},
            "include": [],
            "includeIsRegex": False,
            "exclude": [],
            "excludeIsRegex": False,
        },
        "sourceField": field,
    }


def number_metric_col(label, field, operation="median"):
    return {
        "dataType": "number",
        "isBucketed": False,
        "label": label,
        "operationType": operation,
        "params": {"emptyAsNull": False},
        "sourceField": field,
    }


def unique_count_col(label, field):
    return {
        "dataType": "number",
        "isBucketed": False,
        "label": label,
        "operationType": "unique_count",
        "params": {"emptyAsNull": False},
        "sourceField": field,
    }


def date_histogram_col(interval="auto"):
    return {
        "dataType": "date",
        "isBucketed": True,
        "label": "@timestamp",
        "operationType": "date_histogram",
        "params": {"dropPartials": False, "includeEmptyRows": True, "interval": interval},
        "sourceField": "@timestamp",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Visualization structure builders
# ─────────────────────────────────────────────────────────────────────────────

def xy_visualization(layer_id, x_col_id, y_col_ids, series_type="bar_stacked",
                     title_x="Time", title_y="Count"):
    accessors = y_col_ids if isinstance(y_col_ids, list) else [y_col_ids]
    return {
        "axisTitlesVisibilitySettings": {"x": True, "yLeft": True, "yRight": False},
        "fittingFunction": "Linear",
        "gridlinesVisibilitySettings": {"x": True, "yLeft": True, "yRight": False},
        "labelsOrientation": {"x": 45, "yLeft": 0, "yRight": 0},
        "layers": [{
            "accessors": accessors,
            "layerId": layer_id,
            "layerType": "data",
            "position": "top",
            "seriesType": series_type,
            "showGridlines": True,
            "xAccessor": x_col_id,
        }],
        "legend": {"isVisible": True, "position": "right"},
        "preferredSeriesType": series_type,
        "tickLabelsVisibilitySettings": {"x": True, "yLeft": True, "yRight": False},
        "valueLabels": "hide",
        "xAxisTitle": title_x,
        "yAxisTitle": title_y,
    }


def pie_visualization(layer_id, group_col_id, metric_col_id, shape="donut"):
    return {
        "shape": shape,
        "layers": [{
            "layerId": layer_id,
            "layerType": "data",
            "primaryGroups": [group_col_id],
            "metrics": [metric_col_id],
            "numberDisplay": "percent",
            "categoryDisplay": "default",
            "legendDisplay": "default",
            "nestedLegend": False,
        }],
    }


def datatable_vis(layer_id, col_ids, sort_col):
    """Correct lnsDatatable visualization structure."""
    return {
        "layers": [{
            "layerId": layer_id,
            "layerType": "data",
            "columns": [{"columnId": c, "isTransposed": False} for c in col_ids],
            "sorting": {"columnId": sort_col, "direction": "desc"},
            "rowHeight": "single",
            "rowHeightLines": 1,
            "headerRowHeight": "single",
            "headerRowHeightLines": 1,
        }],
    }


def metric_visualization(layer_id, metric_col_id, subtitle=""):
    """Correct lnsMetric visualization structure for Kibana 8."""
    return {
        "layerId": layer_id,
        "layerType": "data",
        "metricAccessor": metric_col_id,
        "subtitle": subtitle,
        "progressDirection": "auto",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Saved object builders
# ─────────────────────────────────────────────────────────────────────────────

def lens_obj(vis_id, title, vis_type, layer_id, layer, visualization, dv_id,
             filters=None, description=""):
    return {
        "type": "lens",
        "id": vis_id,
        "managed": False,
        "attributes": {
            "description": description,
            "title": title,
            "version": 1,
            "visualizationType": vis_type,
            "state": {
                "adHocDataViews": {},
                "internalReferences": [],
                "filters": filters or [],
                "query": {"language": "kuery", "query": ""},
                "datasourceStates": {
                    "formBased": {"layers": {layer_id: layer}},
                    "indexpattern": {"layers": {}},
                    "textBased": {"layers": {}},
                },
                "visualization": visualization,
            },
        },
        "references": [{"id": dv_id, "name": f"indexpattern-datasource-layer-{layer_id}", "type": "index-pattern"}],
        "coreMigrationVersion": "8.8.0",
        "typeMigrationVersion": "10.1.0",
    }


def make_dashboard(dash_id, title, desc, panels_config):
    """
    panels_config: list of (vis_dict, width, height)
    width/height in Kibana grid units (max 48 wide)
    """
    panels = []
    refs = []
    cx, cy = 0, 0
    row_max_h = 0
    max_w = 48

    for idx, (vis, width, height) in enumerate(panels_config, start=1):
        vis_id = vis["id"]
        if cx + width > max_w:
            cx = 0
            cy += row_max_h
            row_max_h = 0
        panels.append({
            "panelIndex": str(idx),
            "type": "lens",
            "panelRefName": f"panel_{vis_id}",
            "gridData": {"x": cx, "y": cy, "w": width, "h": height, "i": str(idx)},
            "embeddableConfig": {},
        })
        refs.append({"name": f"panel_{vis_id}", "type": "lens", "id": vis_id})
        cx += width
        row_max_h = max(row_max_h, height)

    return {
        "type": "dashboard",
        "id": dash_id,
        "managed": False,
        "attributes": {
            "title": title,
            "description": desc,
            "panelsJSON": json.dumps(panels),
            "optionsJSON": json.dumps({
                "useMargins": True,
                "syncColors": True,
                "hidePanelTitles": False,
                "query": {"language": "kuery", "query": ""},
                "timeRestore": True,
            }),
            "timeRestore": True,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({
                    "query": {"query": "", "language": "kuery"},
                    "filter": [],
                })
            },
            "version": 1,
        },
        "references": refs,
        "coreMigrationVersion": "8.8.0",
    }


# ─────────────────────────────────────────────────────────────────────────────
# High-level visualization factories
# ─────────────────────────────────────────────────────────────────────────────

def build_xy_time(dv_id, vis_id, title, base_filter=None, series="bar_stacked", description=""):
    lid = uid(); cx = uid(); cy = uid()
    layer = make_layer({cx: date_histogram_col(), cy: count_col()}, [cx, cy], lid)
    return lens_obj(vis_id, title, "lnsXY", lid, layer,
                    xy_visualization(lid, cx, cy, series), dv_id, base_filter, description)


def build_pie(dv_id, vis_id, title, field, base_filter=None, shape="donut", size=10, description=""):
    lid = uid(); cg = uid(); cm = uid()
    layer = make_layer(
        {cg: terms_col(field.split(".")[-1].capitalize(), field, cm, size=size), cm: count_col()},
        [cg, cm], lid
    )
    return lens_obj(vis_id, title, "lnsPie", lid, layer,
                    pie_visualization(lid, cg, cm, shape), dv_id, base_filter, description)


def build_metric(dv_id, vis_id, title, op="count", source_field=None,
                 base_filter=None, subtitle="", description=""):
    lid = uid(); cm = uid()
    if op == "count":
        col = count_col(title)
    elif op == "unique_count":
        col = unique_count_col(title, source_field)
    else:
        col = {
            "dataType": "number",
            "isBucketed": False,
            "label": title,
            "operationType": op,
            "params": {"emptyAsNull": False},
            "sourceField": source_field,
        }
    layer = make_layer({cm: col}, [cm], lid)
    return lens_obj(vis_id, title, "lnsMetric", lid, layer,
                    metric_visualization(lid, cm, subtitle), dv_id, base_filter, description)


def build_datatable(dv_id, vis_id, title, struct, sort_idx=-1, base_filter=None, description=""):
    """
    struct: list of (label, dtype, field_or_op)
      dtype: "terms" | "count" | "unique_count" | "number"
      field_or_op for "number": (field, aggregation_op)
    """
    lid = uid()
    cols = {}
    col_order = []

    for label, dtype, field_or_op in struct:
        cid = uid()
        col_order.append(cid)
        if dtype == "terms":
            cols[cid] = terms_col_all(label, field_or_op, "dummy")
        elif dtype == "number":
            cols[cid] = number_metric_col(label, field_or_op[0], field_or_op[1])
        elif dtype == "count":
            cols[cid] = count_col(label)
        elif dtype == "unique_count":
            cols[cid] = unique_count_col(label, field_or_op)

    # Fix placeholder sort references in terms columns
    for cid in cols:
        if cols[cid].get("operationType") == "terms":
            cols[cid]["params"]["orderBy"]["columnId"] = col_order[sort_idx]

    layer = make_layer(cols, col_order, lid)
    return lens_obj(vis_id, title, "lnsDatatable", lid, layer,
                    datatable_vis(lid, col_order, col_order[sort_idx]),
                    dv_id, base_filter, description)


# ─────────────────────────────────────────────────────────────────────────────
# Filter helpers
# ─────────────────────────────────────────────────────────────────────────────

def type_filter(event_types):
    if isinstance(event_types, str):
        return [{
            "meta": {"type": "phrase", "disabled": False, "negate": False, "key": "type"},
            "query": {"match_phrase": {"type": event_types}},
        }]
    return [{
        "meta": {"type": "custom", "disabled": False, "negate": False},
        "query": {"bool": {
            "should": [{"term": {"type": t}} for t in event_types],
            "minimum_should_match": 1,
        }},
    }]


def term_filter(field, value, negate=False):
    return [{
        "meta": {"type": "phrase", "disabled": False, "negate": negate, "key": field},
        "query": {"match_phrase": {field: value}},
    }]


# ─────────────────────────────────────────────────────────────────────────────
# THE ONE COMPREHENSIVE DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

ALL_ERROR_TYPES = [
    "js-error", "console-error", "unhandled-rejection", "selector-error",
    "xpath-error", "selector-miss", "fetch-error", "xhr-error",
    "resource-error",
    "websocket-error", "websocket-unclean-close", "form-validation-failure",
    "csp-violation", "angular-zone-error", "angular-framework-error",
    "angular-change-detection-error", "angular-zone-unstable",
    "react-error-boundary-triggered",
    "react-render-error", "react-hydration-mismatch", "react-root-render-crash",
    "vue-error",
    "nextjs-runtime-error", "nuxt-error", "jquery-ajax-error",
    "jquery-deferred-error",
    "blocking-overlay-detected",
]


def get_comprehensive_dashboard(dv_id):
    """
    Single, comprehensive dashboard covering all log types from performance.js.
    Sections:
      1. Summary KPIs
      2. Global Timeline
      3. Event & Severity Distribution
      4. Errors (JS, Console, Unhandled Rejections, CSP)
      5. Network (Requests, Failures, Slow)
      6. Selectors & XPath
      7. User Interactions & Forms
      8. Navigation & Page Loads
      9. DOM Mutations
      10. Security Events
      11. Automation Detection
      12. Framework Errors (React / Angular / Vue)
      13. Dialogs & Keyboard Actions
      14. Element Inspection & Page Health
      15. Transport Health & Session Lifecycle
    """

    # ── 1. SUMMARY KPIs ──────────────────────────────────────────────────────
    v_total   = build_metric(dv_id, "v_kpi_total", "Total Events",
                             subtitle="All captured log events", description="Count of all events in the index")
    v_errors  = build_metric(dv_id, "v_kpi_errors", "Total Errors",
                             base_filter=type_filter(ALL_ERROR_TYPES),
                             subtitle="All error-type events", description="Count of all error events")
    v_sessions = build_metric(dv_id, "v_kpi_sessions", "Unique Sessions",
                              op="unique_count", source_field="sessionId",
                              subtitle="Distinct browser sessions", description="Unique sessionId values")
    v_urls    = build_metric(dv_id, "v_kpi_urls", "Unique URLs",
                             op="unique_count", source_field="url",
                             subtitle="Distinct monitored pages", description="Unique url values")
    v_high_sev = build_metric(dv_id, "v_kpi_high_sev", "High Severity Events",
                              base_filter=term_filter("severity", "high"),
                              subtitle="severity = high", description="Events with severity=high")
    v_critical = build_metric(dv_id, "v_kpi_critical", "Critical Events",
                              base_filter=term_filter("severity", "critical"),
                              subtitle="severity = critical", description="Events with severity=critical")

    # ── 2. GLOBAL TIMELINE ────────────────────────────────────────────────────
    v_global_ts = build_xy_time(dv_id, "v_global_ts", "All Events — Timeline",
                                series="bar_stacked", description="All events over time")
    v_error_ts  = build_xy_time(dv_id, "v_error_ts",  "Error Events — Timeline",
                                base_filter=type_filter(ALL_ERROR_TYPES), series="area",
                                description="All error events over time")

    # ── 3. EVENT & SEVERITY DISTRIBUTION ─────────────────────────────────────
    v_all_types   = build_pie(dv_id, "v_dist_types", "Events by Type",
                              "type", shape="pie", size=20,
                              description="Top 20 event types")
    v_severity    = build_pie(dv_id, "v_dist_severity", "Events by Severity",
                              "severity", shape="donut",
                              description="Severity breakdown")
    v_top_events  = build_datatable(dv_id, "v_top_events", "Top Event Types (All Time)",
        [("Event Type", "terms", "type"), ("Count", "count", None)],
        sort_idx=1, description="Ranked list of all event types")
    v_top_urls    = build_datatable(dv_id, "v_top_urls", "Most Active Pages",
        [("URL", "terms", "url"), ("Events", "count", None), ("Sessions", "unique_count", "sessionId")],
        sort_idx=1, description="Pages with most events")

    # ── 4a. JAVASCRIPT ERRORS ─────────────────────────────────────────────────
    js_filter = type_filter(["js-error", "unhandled-rejection"])
    v_js_ts   = build_xy_time(dv_id, "v_js_ts", "JS Errors — Timeline",
                              base_filter=js_filter, series="area",
                              description="JS errors and unhandled rejections over time")
    v_js_table = build_datatable(dv_id, "v_js_table", "JavaScript Errors — Details",
        [("Message", "terms", "message.keyword"), ("File", "terms", "filename"),
         ("Line", "number", ("lineno", "median")), ("Severity", "terms", "severity"),
         ("Count", "count", None)],
        sort_idx=4, base_filter=type_filter("js-error"),
        description="Distinct JS error messages with frequency")
    v_unhandled = build_datatable(dv_id, "v_unhandled", "Unhandled Promise Rejections",
        [("Message", "terms", "message.keyword"), ("Page", "terms", "url"),
         ("Count", "count", None)],
        sort_idx=2, base_filter=type_filter("unhandled-rejection"),
        description="Unhandled promise rejections by message")

    # ── 4b. CONSOLE ERRORS / WARNINGS ────────────────────────────────────────
    v_con_err  = build_datatable(dv_id, "v_con_err", "Console Errors",
        [("Message", "terms", "message.keyword"), ("Page", "terms", "url"),
         ("Count", "count", None)],
        sort_idx=2, base_filter=type_filter("console-error"),
        description="Browser console error messages")
    v_con_warn = build_datatable(dv_id, "v_con_warn", "Console Warnings",
        [("Message", "terms", "message.keyword"), ("Page", "terms", "url"),
         ("Count", "count", None)],
        sort_idx=2, base_filter=type_filter("console-warn"),
        description="Browser console warning messages")

    # ── 5. NETWORK ────────────────────────────────────────────────────────────
    net_all_filter = type_filter(["fetch-error", "fetch-success", "fetch-slow",
                                  "xhr-error", "xhr-success", "xhr-slow",
                                  "resource-error"])
    net_err_filter = type_filter(["fetch-error", "xhr-error", "resource-error"])

    v_net_ts   = build_xy_time(dv_id, "v_net_ts", "Network Events — Timeline",
                               base_filter=net_all_filter, series="line",
                               description="Network request events over time")
    v_net_dist = build_pie(dv_id, "v_net_dist", "Network Events by Type",
                           "type", base_filter=net_all_filter, shape="donut", size=10,
                           description="Distribution of network event types")
    v_net_fail = build_datatable(dv_id, "v_net_fail", "Failed Network Requests",
        [("Type", "terms", "type"), ("URL / Endpoint", "terms", "url"),
         ("HTTP Status", "terms", "status"), ("Error Message", "terms", "message.keyword"),
         ("Count", "count", None)],
        sort_idx=4, base_filter=net_err_filter,
        description="Failed fetch / XHR / resource requests")
    v_net_slow = build_datatable(dv_id, "v_net_slow", "Slow Network Requests",
        [("Type", "terms", "type"), ("URL", "terms", "url"),
         ("Avg Duration (ms)", "number", ("duration", "avg")),
         ("Max Duration (ms)", "number", ("duration", "max")),
         ("Count", "count", None)],
        sort_idx=4, base_filter=type_filter(["fetch-slow", "xhr-slow"]),
        description="Slow fetch/XHR requests by endpoint")

    # ── 6. SELECTORS & XPATH ──────────────────────────────────────────────────
    sel_filter = type_filter(["selector-miss", "selector-error", "selector-found", "xpath-error"])
    v_sel_ts   = build_xy_time(dv_id, "v_sel_ts", "Selector Events — Timeline",
                               base_filter=sel_filter, series="area",
                               description="Selector/XPath query activity over time")
    v_sel_dist = build_pie(dv_id, "v_sel_dist", "Selector Events by Type",
                           "type", base_filter=sel_filter, shape="donut",
                           description="Breakdown of selector event types")

    css_miss_filter = [{
        "meta": {"type": "custom", "disabled": False, "negate": False},
        "query": {"bool": {
            "must": [{"term": {"type": "selector-miss"}}],
            "must_not": [{"term": {"method": "xpath"}}],
        }},
    }]
    v_css_miss = build_datatable(dv_id, "v_css_miss", "Missing CSS Selectors",
        [("Selector", "terms", "selector"), ("Method", "terms", "method"),
         ("Miss Count (max)", "number", ("missCount", "max")),
         ("Likely Issue", "terms", "likelyIssue"), ("Page", "terms", "url"),
         ("Occurrences", "count", None)],
        sort_idx=5, base_filter=css_miss_filter,
        description="CSS selectors that failed to find elements")

    xpath_miss_filter = [{
        "meta": {"type": "custom", "disabled": False, "negate": False},
        "query": {"bool": {
            "should": [
                {"term": {"type": "xpath-error"}},
                {"bool": {"must": [{"term": {"type": "selector-miss"}}, {"term": {"method": "xpath"}}]}},
            ],
            "minimum_should_match": 1,
        }},
    }]
    v_xpath_miss = build_datatable(dv_id, "v_xpath_miss", "XPath Errors & Misses",
        [("XPath Expression", "terms", "xpath"), ("Type", "terms", "type"),
         ("Message", "terms", "message.keyword"), ("Miss Count (max)", "number", ("missCount", "max")),
         ("Page", "terms", "url"), ("Occurrences", "count", None)],
        sort_idx=5, base_filter=xpath_miss_filter,
        description="XPath expressions that failed or missed")

    # ── 7. USER INTERACTIONS & FORMS ─────────────────────────────────────────
    int_filter = type_filter(["user-click", "click-on-disabled", "programmatic-click",
                               "rapid-clicks", "form-submission",
                               "form-validation-failure", "value-manipulation"])
    v_int_ts   = build_xy_time(dv_id, "v_int_ts", "User Interactions — Timeline",
                               base_filter=int_filter, series="area",
                               description="User activity events over time")
    v_int_dist = build_pie(dv_id, "v_int_dist", "Interaction Events by Type",
                           "type", base_filter=int_filter, shape="donut",
                           description="Distribution of interaction types")
    v_form_sub = build_datatable(dv_id, "v_form_sub", "Form Submissions",
        [("Form Action", "terms", "formAction"), ("Method", "terms", "method"),
         ("Page", "terms", "url"), ("Count", "count", None)],
        sort_idx=3, base_filter=type_filter("form-submission"),
        description="Form submission events by endpoint")
    v_form_val = build_datatable(dv_id, "v_form_val", "Form Validation Failures",
        [("Form Action", "terms", "formAction"), ("Page", "terms", "url"),
         ("Count", "count", None)],
        sort_idx=2, base_filter=type_filter("form-validation-failure"),
        description="Form fields that failed validation")

    # ── 8. NAVIGATION & PAGE LOADS ────────────────────────────────────────────
    nav_filter = type_filter(["page-load", "hashchange", "pushState", "replaceState", "connection"])
    v_nav_ts   = build_xy_time(dv_id, "v_nav_ts", "Navigation Events — Timeline",
                               base_filter=nav_filter, series="line",
                               description="Navigation events over time")
    v_nav_dist = build_pie(dv_id, "v_nav_dist", "Navigation Events by Type",
                           "type", base_filter=nav_filter, shape="pie",
                           description="Distribution of navigation event types")
    v_page_load = build_datatable(dv_id, "v_page_load", "Page Load Performance",
        [("Page URL", "terms", "url"),
         ("Avg Load Time (ms)", "number", ("loadTime", "avg")),
         ("Max Load Time (ms)", "number", ("loadTime", "max")),
         ("Load Events", "count", None)],
        sort_idx=1, base_filter=type_filter("page-load"),
        description="Page load times per URL")

    # ── 9. DOM MUTATIONS ──────────────────────────────────────────────────────
    dom_filter = type_filter(["dom-mutations", "dom-attribute-changes"])
    v_dom_ts   = build_xy_time(dv_id, "v_dom_ts", "DOM Mutations — Timeline",
                               base_filter=dom_filter, series="bar",
                               description="DOM mutation events over time")
    v_dom_table = build_datatable(dv_id, "v_dom_table", "DOM Mutation Details",
        [("Type", "terms", "type"),
         ("Nodes Added (max)", "number", ("nodesAdded", "max")),
         ("Nodes Removed (max)", "number", ("nodesRemoved", "max")),
         ("Total Changes (max)", "number", ("totalChanges", "max")),
         ("Page", "terms", "url"), ("Count", "count", None)],
        sort_idx=5, base_filter=dom_filter,
        description="DOM change statistics per page")

    # ── 10. SECURITY EVENTS ───────────────────────────────────────────────────
    sec_filter = type_filter(["csp-violation", "websocket-error",
                               "websocket-unclean-close", "blocking-overlay-detected"])
    v_sec_ts   = build_xy_time(dv_id, "v_sec_ts", "Security Events — Timeline",
                               base_filter=sec_filter, series="bar_stacked",
                               description="Security-related events over time")
    v_sec_dist = build_pie(dv_id, "v_sec_dist", "Security Events by Type",
                           "type", base_filter=sec_filter, shape="donut",
                           description="Distribution of security event types")
    v_csp      = build_datatable(dv_id, "v_csp", "CSP Violations",
        [("Blocked URI", "terms", "blockedURI"), ("Violated Directive", "terms", "violatedDirective"),
         ("Source", "terms", "source"), ("Count", "count", None)],
        sort_idx=3, base_filter=type_filter("csp-violation"),
        description="Content Security Policy violations by resource")

    # ── 11. AUTOMATION DETECTION ──────────────────────────────────────────────
    auto_filter = type_filter(["automation-detected", "programmatic-click",
                                "rapid-clicks"])
    v_auto_ts   = build_xy_time(dv_id, "v_auto_ts", "Automation Detection — Timeline",
                                base_filter=auto_filter, series="bar_stacked",
                                description="Automation/suspicious events over time")
    v_auto_dist = build_pie(dv_id, "v_auto_dist", "Automation Event Types",
                            "type", base_filter=auto_filter, shape="donut",
                            description="Distribution of automation detection event types")
    v_auto_table = build_datatable(dv_id, "v_auto_table", "Automation — Session Details",
        [("Session ID", "terms", "sessionId"), ("Event Type", "terms", "type"),
         ("Page", "terms", "url"), ("Count", "count", None)],
        sort_idx=3, base_filter=auto_filter,
        description="Sessions with automation signals")

    # ── 12. FRAMEWORK ERRORS ──────────────────────────────────────────────────
    fw_filter = type_filter(["frameworks-detected",
                              "react-error-boundary-triggered", "react-render-error",
                              "react-hydration-mismatch", "react-key-warning",
                              "react-function-component-warning", "react-root-render-crash",
                              "angular-zone-error", "angular-framework-error",
                              "angular-change-detection-error", "angular-zone-unstable",
                              "vue-error", "vue-warning",
                              "jquery-ajax-error", "jquery-deferred-error",
                              "nextjs-runtime-error", "nuxt-error"])
    v_fw_ts   = build_xy_time(dv_id, "v_fw_ts", "Framework Events — Timeline",
                              base_filter=fw_filter, series="bar_stacked",
                              description="Framework-level events over time")
    v_fw_dist = build_pie(dv_id, "v_fw_dist", "Framework Events by Type",
                          "type", base_filter=fw_filter, shape="donut", size=20,
                          description="Distribution of framework event types")
    v_react   = build_datatable(dv_id, "v_react", "React Errors",
        [("Type", "terms", "type"), ("Component", "terms", "componentName"),
         ("Message", "terms", "message.keyword"), ("Count", "count", None)],
        sort_idx=3,
        base_filter=type_filter(["react-error-boundary-triggered", "react-render-error",
                                  "react-hydration-mismatch"]),
        description="React framework errors by component")
    v_angular = build_datatable(dv_id, "v_angular", "Angular Errors",
        [("Type", "terms", "type"), ("Zone", "terms", "zoneName"),
         ("Message", "terms", "message.keyword"), ("Count", "count", None)],
        sort_idx=3,
        base_filter=type_filter(["angular-zone-error", "angular-framework-error",
                                  "angular-change-detection-error"]),
        description="Angular framework errors by zone")
    v_vue     = build_datatable(dv_id, "v_vue", "Vue Errors & Warnings",
        [("Type", "terms", "type"), ("Message", "terms", "message.keyword"),
         ("Count", "count", None)],
        sort_idx=2, base_filter=type_filter(["vue-error", "vue-warning"]),
        description="Vue.js errors and warnings")

    # ── 13. DIALOGS & KEYBOARD ACTIONS ─────────────────────────────────────
    dialog_filter = type_filter("dialog-opened")
    v_dialog_table = build_datatable(dv_id, "v_dialog_table", "Browser Dialogs (alert / confirm / prompt)",
        [("Dialog Type", "terms", "dialogType"), ("Message", "terms", "message.keyword"),
         ("Page", "terms", "url"), ("Session", "terms", "sessionId"),
         ("Count", "count", None)],
        sort_idx=4, base_filter=dialog_filter,
        description="Browser dialog events intercepted from alert, confirm, and prompt calls")

    kb_filter = type_filter("keyboard-action")
    v_kb_table = build_datatable(dv_id, "v_kb_table", "Keyboard Actions (Automation)",
        [("Key", "terms", "key"), ("Modifiers", "terms", "modifiers"),
         ("Target Tag", "terms", "targetTagName"),
         ("Count", "count", None)],
        sort_idx=3, base_filter=kb_filter,
        description="Special key presses and shortcuts during automated sessions")

    # ── 14. ELEMENT INSPECTION & PAGE HEALTH ─────────────────────────────────
    inspect_filter = type_filter("element-inspection")
    v_inspect_table = build_datatable(dv_id, "v_inspect_table", "Element Inspections (Automation)",
        [("Method", "terms", "method"), ("Element", "terms", "xpath"),
         ("Page", "terms", "url"), ("Count", "count", None)],
        sort_idx=3, base_filter=inspect_filter,
        description="getBoundingClientRect / getComputedStyle / offset* calls during automation")

    idle_filter = type_filter("page-idle")
    v_idle_table = build_datatable(dv_id, "v_idle_table", "Page Idle Events — Stuck Tests",
        [("Page", "terms", "url"), ("Max Idle (ms)", "number", ("idleMs", "max")),
         ("Session", "terms", "sessionId"), ("Count", "count", None)],
        sort_idx=3, base_filter=idle_filter,
        description="Pages where no user activity occurred for 30+ seconds — tests may be stuck")

    # ── 15. TRANSPORT HEALTH & SESSION LIFECYCLE ─────────────────────────────
    transport_filter = type_filter(["queue-overflow", "batch-dropped", "session-end"])
    v_transport_ts = build_xy_time(dv_id, "v_transport_ts", "Transport & Session Events — Timeline",
                                   base_filter=transport_filter, series="bar_stacked",
                                   description="Queue overflows, dropped batches, and session endings over time")

    v_overflow_table = build_datatable(dv_id, "v_overflow_table", "Queue Overflows & Dropped Batches",
        [("Type", "terms", "type"),
         ("Dropped Count (max)", "number", ("droppedCount", "max")),
         ("Queue Size (max)", "number", ("queueSize", "max")),
         ("Retry Attempts (max)", "number", ("retryAttempts", "max")),
         ("Session", "terms", "sessionId"), ("Count", "count", None)],
        sort_idx=5, base_filter=type_filter(["queue-overflow", "batch-dropped"]),
        description="Events lost due to queue overflow or network failures")

    v_session_table = build_datatable(dv_id, "v_session_table", "Session End Events",
        [("Reason", "terms", "reason"), ("Events in Queue (max)", "number", ("totalEventsInQueue", "max")),
         ("Session", "terms", "sessionId"), ("Page", "terms", "url"),
         ("Count", "count", None)],
        sort_idx=4, base_filter=type_filter("session-end"),
        description="How browser sessions ended (beforeunload, pagehide, visibilitychange)")

    v_connection_table = build_datatable(dv_id, "v_connection_table", "Connection Status Changes",
        [("Status", "terms", "status"), ("Page", "terms", "url"),
         ("Session", "terms", "sessionId"), ("Count", "count", None)],
        sort_idx=3, base_filter=type_filter("connection"),
        description="Browser online/offline connection status events")

    v_value_table = build_datatable(dv_id, "v_value_table", "Value Manipulations (Automation)",
        [("Method", "terms", "method"), ("Element", "terms", "xpath"),
         ("Page", "terms", "url"), ("Count", "count", None)],
        sort_idx=3, base_filter=type_filter("value-manipulation"),
        description="Programmatic input/select/textarea value changes during automation")

    # ── DASHBOARD PANEL LAYOUT ────────────────────────────────────────────────
    # Grid is 48 units wide. Heights are also in grid units.
    panels = [
        # ── Section 1: KPI Summary Row ──
        (v_total,     8, 8), (v_errors,   8, 8), (v_sessions,  8, 8),
        (v_urls,      8, 8), (v_high_sev, 8, 8), (v_critical,  8, 8),

        # ── Section 2: Global Timelines ──
        (v_global_ts, 24, 14), (v_error_ts,  24, 14),

        # ── Section 3: Event & Severity Distribution ──
        (v_all_types,  24, 14), (v_severity,   24, 14),
        (v_top_events, 24, 14), (v_top_urls,   24, 14),

        # ── Section 4: JavaScript Errors ──
        (v_js_ts,    48, 12),
        (v_js_table, 32, 16), (v_unhandled, 16, 16),
        (v_con_err,  24, 14), (v_con_warn,  24, 14),

        # ── Section 5: Network ──
        (v_net_ts,   24, 12), (v_net_dist, 24, 12),
        (v_net_fail, 48, 16),
        (v_net_slow, 48, 14),

        # ── Section 6: Selectors & XPath ──
        (v_sel_ts,    24, 12), (v_sel_dist, 24, 12),
        (v_css_miss,  24, 16), (v_xpath_miss, 24, 16),

        # ── Section 7: User Interactions & Forms ──
        (v_int_ts,   24, 12), (v_int_dist, 24, 12),
        (v_form_sub, 24, 14), (v_form_val, 24, 14),

        # ── Section 8: Navigation & Page Loads ──
        (v_nav_ts,    24, 12), (v_nav_dist,  24, 12),
        (v_page_load, 48, 14),

        # ── Section 9: DOM Mutations ──
        (v_dom_ts,    24, 12), (v_dom_table, 24, 14),

        # ── Section 10: Security ──
        (v_sec_ts,   24, 12), (v_sec_dist, 24, 12),
        (v_csp,      48, 14),

        # ── Section 11: Automation Detection ──
        (v_auto_ts,    24, 12), (v_auto_dist,  24, 12),
        (v_auto_table, 48, 14),

        # ── Section 12: Framework Errors ──
        (v_fw_ts,   24, 12), (v_fw_dist, 24, 12),
        (v_react,   16, 16), (v_angular, 16, 16), (v_vue, 16, 16),

        # ── Section 13: Dialogs & Keyboard Actions ──
        (v_dialog_table, 24, 14), (v_kb_table, 24, 14),

        # ── Section 14: Element Inspection & Page Health ──
        (v_inspect_table, 24, 14), (v_idle_table, 24, 14),

        # ── Section 15: Transport Health & Session Lifecycle ──
        (v_transport_ts, 48, 12),
        (v_overflow_table, 24, 14), (v_session_table, 24, 14),
        (v_connection_table, 24, 14), (v_value_table, 24, 14),
    ]

    all_vis  = [p[0] for p in panels]
    dash = make_dashboard(
        "dashboard-main",
        "Selenium Monitoring — Comprehensive Dashboard",
        (
            "Full visibility into all Selenium monitoring event types: "
            "KPIs, timelines, JS errors, network requests, selector failures, "
            "user interactions, navigation, DOM mutations, security events, "
            "automation detection, framework errors, dialogs, keyboard actions, "
            "element inspection, page idle detection, and transport health."
        ),
        panels,
    )
    return all_vis + [dash]


# ─────────────────────────────────────────────────────────────────────────────
# Field Mapping Configuration for Kibana
# ─────────────────────────────────────────────────────────────────────────────

def configure_field_mappings():
    """Configure field mappings for unmapped fields from performance.js"""
    logger.info("[ES] Configuring field mappings...")

    index_template_payload = {
        "index_patterns": ["selenium-events*"],
        "template": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            "mappings": {
                "dynamic": "true",
                "properties": {
                    # Core
                    "@timestamp":      {"type": "date"},
                    "timestamp":       {"type": "date"},
                    "time":            {"type": "date"},
                    "client_time":     {"type": "date"},
                    "type":            {"type": "keyword"},
                    "severity":        {"type": "keyword"},
                    "sessionId":       {"type": "keyword"},
                    "pageId":          {"type": "keyword"},
                    "correlationId":   {"type": "keyword"},
                    "eventId":         {"type": "keyword"},
                    "uniqueId":        {"type": "keyword"},
                    "url":             {"type": "keyword"},
                    "userAgent":       {"type": "text"},
                    "isAutomated":     {"type": "boolean"},
                    "isAutomationDetected": {"type": "boolean"},
                    "isTrusted":       {"type": "boolean"},
                    "uptime":          {"type": "long"},

                    # Selector
                    "method":          {"type": "keyword"},
                    "selector":        {"type": "keyword"},
                    "selectorPath":    {"type": "keyword"},
                    "xpath":           {"type": "keyword"},
                    "expression":      {"type": "keyword"},
                    "found":           {"type": "boolean"},
                    "isRepeatedFailure": {"type": "boolean"},
                    "missCount":       {"type": "integer"},
                    "matchCount":      {"type": "integer"},
                    "firstAttempt":    {"type": "long"},
                    "lastAttempt":     {"type": "long"},
                    "timeSinceFirst":  {"type": "long"},
                    "likelyIssue":     {"type": "keyword"},

                    # Selector analysis
                    "selectorTagName":    {"type": "keyword"},
                    "selectorId":         {"type": "keyword"},
                    "selectorClasses":    {"type": "keyword"},
                    "selectorAttributes": {"type": "keyword"},
                    "selectorDetails":    {"type": "object"},
                    "xpathAnalysis":      {"type": "object"},
                    "containsText":            {"type": "boolean"},
                    "containsAttribute":       {"type": "boolean"},
                    "containsDescendant":      {"type": "boolean"},
                    "containsAxis":            {"type": "boolean"},
                    "pseudoClasses":           {"type": "keyword"},
                    "combinators":             {"type": "keyword"},

                    # Parent path
                    "parentPath":      {"type": "keyword"},
                    "parentTagName":   {"type": "keyword"},
                    "parentId":        {"type": "keyword"},
                    "parentClasses":   {"type": "keyword"},

                    # Automation context
                    "automationContext": {"type": "boolean"},

                    # Error
                    "message": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 2048}},
                    },
                    "filename":        {"type": "keyword"},
                    "source":          {"type": "keyword"},
                    "lineno":          {"type": "integer"},
                    "colno":           {"type": "integer"},
                    "stack":           {"type": "text"},
                    "args":            {"type": "text"},
                    "errorThrown":     {"type": "keyword"},
                    "errorCode":       {"type": "keyword"},
                    "reason":          {"type": "text"},
                    "code":            {"type": "integer"},
                    "warning":         {"type": "keyword"},

                    # Network
                    "requestMethod":   {"type": "keyword"},
                    "requestUrl":      {"type": "keyword"},
                    "status":          {"type": "keyword"},
                    "statusCode":      {"type": "integer"},
                    "duration":        {"type": "long"},
                    "success":         {"type": "boolean"},
                    "pendingRequests": {"type": "integer"},

                    # Performance
                    "loadTime":    {"type": "long"},
                    "idleMs":      {"type": "long"},
                    "interval":    {"type": "long"},
                    "slow":        {"type": "boolean"},

                    # DOM
                    "tagName":      {"type": "keyword"},
                    "tag":          {"type": "keyword"},
                    "src":          {"type": "keyword"},
                    "textContent":  {"type": "text"},
                    "target":       {"type": "keyword"},
                    "position":     {"type": "keyword"},
                    "nodesAdded":   {"type": "integer"},
                    "nodesRemoved": {"type": "integer"},
                    "totalRemoved": {"type": "integer"},
                    "changes":      {"type": "object"},
                    "totalChanges": {"type": "integer"},
                    "removedElements": {"type": "keyword"},
                    "count":        {"type": "integer"},
                    "clickCount":   {"type": "integer"},
                    "attribute":    {"type": "keyword"},

                    # Form
                    "formAction":    {"type": "keyword"},
                    "formMethod":    {"type": "keyword"},
                    "invalidFields": {"type": "object"},
                    "inputType":     {"type": "keyword"},
                    "checked":       {"type": "boolean"},
                    "value_length":  {"type": "integer"},
                    "value_preview": {"type": "text"},

                    # Navigation
                    "from": {"type": "keyword"},
                    "to":   {"type": "keyword"},

                    # Security / CSP
                    "blockedURI":        {"type": "keyword"},
                    "violatedDirective": {"type": "keyword"},
                    "originalPolicy":    {"type": "keyword"},

                    # Framework
                    "frameworks":      {"type": "object"},
                    "componentName":   {"type": "keyword"},
                    "componentStack":  {"type": "keyword"},
                    "zoneName":        {"type": "keyword"},
                    "info":            {"type": "keyword"},
                    "trace":           {"type": "keyword"},

                    # Value manipulation
                    "oldValue": {"type": "text"},
                    "newValue": {"type": "text"},

                    # Automation
                    "signals":         {"type": "keyword"},
                    "rapidClickCount": {"type": "integer"},

                    # Connection
                    "connection": {"type": "object"},

                    # Overlay
                    "overlay":           {"type": "object"},
                    "zIndex":            {"type": "integer"},
                    "element":           {"type": "keyword"},
                    "elementInspection": {"type": "object"},

                    # Additional fields
                    "pageUrl":           {"type": "keyword"},
                    "details":           {"type": "object"},
                    "text":              {"type": "text"},
                    "name":              {"type": "keyword"},
                    "msg":               {"type": "text"},
                    "gap":               {"type": "integer"},
                    "first":             {"type": "date"},
                    "last":              {"type": "date"},
                    "coverage":          {"type": "integer"},

                    # Dialog tracking
                    "dialogType":        {"type": "keyword"},
                    "result":            {"type": "boolean"},
                    "hasResult":         {"type": "boolean"},

                    # Keyboard tracking
                    "key":               {"type": "keyword"},
                    "keyCode":           {"type": "keyword"},

                    # Queue / transport reliability
                    "droppedCount":      {"type": "integer"},
                    "queueSize":         {"type": "integer"},
                    "retryAttempts":     {"type": "integer"},
                    "totalEventsInQueue": {"type": "integer"},

                    # Page load HTTP status
                    "httpStatus":        {"type": "integer"},

                    # Select element tracking
                    "selectedIndex":     {"type": "integer"},
                    "input_type":        {"type": "keyword"},

                    # Context object (not searchable)
                    "_ctx":              {"type": "object", "enabled": False},

                    # Summary
                    "summary": {"type": "keyword"},
                },
            },
        },
    }

    try:
        res = requests.put(
            f"{ELASTIC_URL}/_index_template/selenium-events-template",
            auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
            json=index_template_payload,
            headers={"Content-Type": "application/json"},
        )
        if res.status_code in (200, 201):
            logger.info("[ES] Field mappings configured successfully")
        else:
            logger.warning(f"[ES] Field mapping config response: {res.status_code} - {res.text}")
    except Exception as e:
        logger.warning(f"[ES] Field mapping config failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Import helpers
# ─────────────────────────────────────────────────────────────────────────────

def import_saved_objects(ndjson: str):
    logger.info("[Kibana] Importing saved objects via _import API...")
    files = {"file": ("export.ndjson", io.BytesIO(ndjson.encode("utf-8")), "application/ndjson")}
    res = session.post(f"{KIBANA_URL}/api/saved_objects/_import?overwrite=true", files=files)

    if res.status_code in (200, 201):
        body = res.json()
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


def deploy_dashboard(name: str, dashboard_func, dv_id: str):
    try:
        logger.info(f"[Deployer] Building {name}...")
        objects = dashboard_func(dv_id)
        ndjson = "\n".join(json.dumps(obj) for obj in objects)
        import_saved_objects(ndjson)
        logger.info(f"[Kibana] {name} successfully deployed!")
        return True
    except Exception as e:
        logger.error(f"[Deployer] Failed to deploy {name}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main Deployment
# ─────────────────────────────────────────────────────────────────────────────

def build_and_deploy():
    wait_for_kibana()
    dv_id = get_or_create_data_view()

    # Clean slate — remove all old dashboards and lens visualizations
    delete_existing_saved_objects()

    # Configure Elasticsearch field mappings
    configure_field_mappings()

    # Deploy the single comprehensive dashboard
    dashboards = [
        ("Comprehensive Dashboard", get_comprehensive_dashboard),
    ]

    success_count = 0
    for name, func in dashboards:
        if deploy_dashboard(name, func, dv_id):
            success_count += 1

    logger.info(f"[Deployer] Deployed {success_count}/{len(dashboards)} dashboards successfully")

    if success_count < len(dashboards):
        logger.warning("[Deployer] Some dashboards failed to deploy")
    else:
        logger.info("[Kibana] All dashboards deployed successfully!")


if __name__ == "__main__":
    configure_kibana_system()
    build_and_deploy()

    # Keep alive for docker
    while True:
        time.sleep(60)