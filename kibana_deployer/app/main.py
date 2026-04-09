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

ELASTIC_INDEX    = os.getenv("ELASTIC_INDEX", "selenium-events")
ILM_MAX_SIZE     = os.getenv("ILM_MAX_SIZE", "1gb")
ILM_MAX_AGE      = os.getenv("ILM_MAX_AGE", "7d")
ILM_MAX_DOCS     = int(os.getenv("ILM_MAX_DOCS", 5000000))
ILM_DELETE_AFTER  = os.getenv("ILM_DELETE_AFTER", "30d")
ILM_POLICY_NAME  = f"{ELASTIC_INDEX}-policy"

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


# ─────────────────────────────────────────────────────────────────────────────
# ILM (Index Lifecycle Management) setup
# ─────────────────────────────────────────────────────────────────────────────

def create_ilm_policy():
    """Create the ILM policy for automatic index rollover and deletion."""
    logger.info(f"[ES] Creating ILM policy '{ILM_POLICY_NAME}'...")
    policy = {
        "policy": {
            "phases": {
                "hot": {
                    "actions": {
                        "rollover": {
                            "max_size": ILM_MAX_SIZE,
                            "max_age": ILM_MAX_AGE,
                            "max_docs": ILM_MAX_DOCS,
                        }
                    }
                },
                "delete": {
                    "min_age": ILM_DELETE_AFTER,
                    "actions": {
                        "delete": {}
                    }
                }
            }
        }
    }
    try:
        res = requests.put(
            f"{ELASTIC_URL}/_ilm/policy/{ILM_POLICY_NAME}",
            auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
            json=policy,
            headers={"Content-Type": "application/json"},
        )
        if res.status_code in (200, 201):
            logger.info(f"[ES] ILM policy '{ILM_POLICY_NAME}' created successfully "
                        f"(rollover: size={ILM_MAX_SIZE}, age={ILM_MAX_AGE}, docs={ILM_MAX_DOCS}, "
                        f"delete_after={ILM_DELETE_AFTER})")
        else:
            logger.error(f"[ES] Failed to create ILM policy: {res.status_code} - {res.text}")
    except Exception as e:
        logger.error(f"[ES] Error creating ILM policy: {e}")


def _is_concrete_index(name):
    """Return True if name exists as a concrete index (not an alias)."""
    try:
        res = requests.get(
            f"{ELASTIC_URL}/{name}",
            auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
            timeout=5,
        )
        if res.status_code != 200:
            return False
        index_data = res.json()
        return name in index_data
    except Exception:
        return False


def _is_alias(name):
    """Return True if name is an alias."""
    try:
        res = requests.get(
            f"{ELASTIC_URL}/_alias/{name}",
            auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
            timeout=5,
        )
        return res.status_code == 200
    except Exception:
        return False


def migrate_existing_index():
    """Handle migration from a concrete index to rollover alias scheme."""
    if _is_alias(ELASTIC_INDEX):
        logger.info(f"[ES] '{ELASTIC_INDEX}' is already an alias — no migration needed.")
        return

    if not _is_concrete_index(ELASTIC_INDEX):
        logger.info(f"[ES] '{ELASTIC_INDEX}' does not exist — fresh deployment, no migration needed.")
        return

    first_index = f"{ELASTIC_INDEX}-000001"
    logger.info(f"[ES] '{ELASTIC_INDEX}' is a concrete index — migrating to rollover scheme...")

    # Check if there are documents to migrate
    try:
        count_res = requests.get(
            f"{ELASTIC_URL}/{ELASTIC_INDEX}/_count",
            auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
            timeout=10,
        )
        doc_count = count_res.json().get("count", 0) if count_res.status_code == 200 else 0
    except Exception:
        doc_count = 0

    if doc_count > 0:
        logger.info(f"[ES] Reindexing {doc_count} documents from '{ELASTIC_INDEX}' to '{first_index}'...")
        reindex_res = requests.post(
            f"{ELASTIC_URL}/_reindex",
            auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
            json={
                "source": {"index": ELASTIC_INDEX},
                "dest": {"index": first_index},
            },
            headers={"Content-Type": "application/json"},
            timeout=600,
        )
        if reindex_res.status_code != 200:
            logger.error(f"[ES] Reindex failed: {reindex_res.status_code} - {reindex_res.text}")
            return
        result = reindex_res.json()
        logger.info(f"[ES] Reindex complete: {result.get('total', 0)} documents processed.")
    else:
        logger.info(f"[ES] No documents in '{ELASTIC_INDEX}', skipping reindex.")

    # Delete the concrete index
    logger.info(f"[ES] Deleting concrete index '{ELASTIC_INDEX}'...")
    del_res = requests.delete(
        f"{ELASTIC_URL}/{ELASTIC_INDEX}",
        auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
        timeout=30,
    )
    if del_res.status_code not in (200, 204):
        logger.error(f"[ES] Failed to delete concrete index: {del_res.status_code} - {del_res.text}")
        return

    # Add write alias to the new index
    if doc_count > 0:
        logger.info(f"[ES] Adding write alias '{ELASTIC_INDEX}' to '{first_index}'...")
        alias_res = requests.post(
            f"{ELASTIC_URL}/_aliases",
            auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
            json={
                "actions": [
                    {"add": {"index": first_index, "alias": ELASTIC_INDEX, "is_write_index": True}}
                ]
            },
            headers={"Content-Type": "application/json"},
        )
        if alias_res.status_code == 200:
            logger.info(f"[ES] Migration complete — '{ELASTIC_INDEX}' is now a write alias.")
        else:
            logger.error(f"[ES] Failed to create alias: {alias_res.status_code} - {alias_res.text}")

    logger.info("[ES] Migration finished.")


def bootstrap_rollover_index():
    """Create the first rollover index with write alias if it doesn't exist."""
    if _is_alias(ELASTIC_INDEX):
        logger.info(f"[ES] Write alias '{ELASTIC_INDEX}' already exists, skipping bootstrap.")
        return

    first_index = f"{ELASTIC_INDEX}-000001"
    logger.info(f"[ES] Bootstrapping rollover index '{first_index}' with write alias '{ELASTIC_INDEX}'...")

    try:
        res = requests.put(
            f"{ELASTIC_URL}/{first_index}",
            auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
            json={
                "aliases": {
                    ELASTIC_INDEX: {"is_write_index": True}
                }
            },
            headers={"Content-Type": "application/json"},
        )
        if res.status_code in (200, 201):
            logger.info(f"[ES] Rollover index '{first_index}' created with write alias '{ELASTIC_INDEX}'.")
        elif res.status_code == 400 and "already exists" in res.text:
            logger.info(f"[ES] Index '{first_index}' already exists, adding alias...")
            alias_res = requests.post(
                f"{ELASTIC_URL}/_aliases",
                auth=(ELASTIC_USERNAME, ELASTIC_PASSWORD),
                json={
                    "actions": [
                        {"add": {"index": first_index, "alias": ELASTIC_INDEX, "is_write_index": True}}
                    ]
                },
                headers={"Content-Type": "application/json"},
            )
            if alias_res.status_code == 200:
                logger.info(f"[ES] Write alias '{ELASTIC_INDEX}' added to '{first_index}'.")
            else:
                logger.error(f"[ES] Failed to add alias: {alias_res.status_code} - {alias_res.text}")
        else:
            logger.error(f"[ES] Failed to bootstrap: {res.status_code} - {res.text}")
    except Exception as e:
        logger.error(f"[ES] Error bootstrapping rollover index: {e}")


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
        "customLabel": True,
        "label": label,
        "operationType": "count",
        "params": {"emptyAsNull": False},
        "sourceField": "___records___",
    }


def terms_col(label, field, order_col_id, size=10, missing_bucket=False, other_bucket=True):
    return {
        "dataType": "string",
        "isBucketed": True,
        "customLabel": True,
        "label": label,
        "operationType": "terms",
        "params": {
            "size": size,
            "orderBy": {"type": "column", "columnId": order_col_id},
            "orderDirection": "desc",
            "otherBucket": other_bucket,
            "missingBucket": missing_bucket,
            "parentFormat": {"id": "terms"},
        },
        "sourceField": field,
    }



def number_metric_col(label, field, operation="median"):
    return {
        "dataType": "number",
        "isBucketed": False,
        "customLabel": True,
        "label": label,
        "operationType": operation,
        "params": {"emptyAsNull": False},
        "sourceField": field,
    }


def unique_count_col(label, field):
    return {
        "dataType": "number",
        "isBucketed": False,
        "customLabel": True,
        "label": label,
        "operationType": "unique_count",
        "params": {"emptyAsNull": False},
        "sourceField": field,
    }


def date_histogram_col(interval="auto"):
    return {
        "dataType": "date",
        "isBucketed": True,
        "customLabel": True,
        "label": "@timestamp",
        "operationType": "date_histogram",
        "params": {"dropPartials": False, "includeEmptyRows": True, "interval": interval},
        "sourceField": "@timestamp",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Visualization structure builders
# ─────────────────────────────────────────────────────────────────────────────

def xy_visualization(layer_id, x_col_id, y_col_ids, series_type="bar_stacked",
                     title_x="Time", title_y="Count", split_col_id=None):
    accessors = y_col_ids if isinstance(y_col_ids, list) else [y_col_ids]
    layer_config = {
        "accessors": accessors,
        "layerId": layer_id,
        "layerType": "data",
        "position": "top",
        "seriesType": series_type,
        "showGridlines": True,
        "xAccessor": x_col_id,
    }
    if split_col_id:
        layer_config["splitAccessor"] = split_col_id
    return {
        "axisTitlesVisibilitySettings": {"x": True, "yLeft": True, "yRight": False},
        "fittingFunction": "Linear",
        "gridlinesVisibilitySettings": {"x": True, "yLeft": True, "yRight": False},
        "labelsOrientation": {"x": 45, "yLeft": 0, "yRight": 0},
        "layers": [layer_config],
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


def datatable_vis(layer_id, col_ids, sort_col, transposed_cols=None):
    """Correct lnsDatatable visualization structure."""
    if transposed_cols is None:
        transposed_cols = set()
    return {
        "layerId": layer_id,
        "layerType": "data",
        "columns": [
            {"columnId": c, "isTransposed": c in transposed_cols}
            for c in col_ids
        ],
        "sorting": {"columnId": sort_col, "direction": "desc"},
        "rowHeight": "single",
        "rowHeightLines": 1,
        "headerRowHeight": "single",
        "headerRowHeightLines": 1,
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


def build_xy_time_split(dv_id, vis_id, title, split_field, split_label=None,
                        split_size=10, base_filter=None, series="line", description=""):
    """XY time chart with one series per term value of split_field."""
    lid = uid(); cx = uid(); cy = uid(); cs = uid()
    if split_label is None:
        split_label = split_field.split(".")[-1].capitalize()
    layer = make_layer(
        {cx: date_histogram_col(), cy: count_col(), cs: terms_col(split_label, split_field, cy, size=split_size)},
        [cx, cs, cy], lid
    )
    return lens_obj(vis_id, title, "lnsXY", lid, layer,
                    xy_visualization(lid, cx, cy, series, split_col_id=cs), dv_id, base_filter, description)


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
            "customLabel": True,
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
    struct: list of (label, dtype, field_or_op[, size])
      dtype: "terms" | "count" | "unique_count" | "number"
      field_or_op for "number": (field, aggregation_op)
      size: optional, only for "terms" dtype (default 10)
    """
    lid = uid()
    cols = {}
    col_order = []

    for item in struct:
        label, dtype, field_or_op = item[0], item[1], item[2]
        size = item[3] if len(item) > 3 else 10
        other_bucket = item[4] if len(item) > 4 else True
        cid = uid()
        col_order.append(cid)
        if dtype == "terms":
            cols[cid] = terms_col(label, field_or_op, "dummy", size=size, other_bucket=other_bucket)
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


def build_pivot_datatable(dv_id, vis_id, title, row_field, row_label,
                          pivot_field, pivot_label, pivot_size=20,
                          row_size=50, base_filter=None, description=""):
    """
    Build a cross-tab / pivot datatable.
    Rows = terms on row_field, columns = transposed terms on pivot_field,
    cells = count metric.
    """
    lid = uid()
    row_cid = uid()
    pivot_cid = uid()
    count_cid = uid()

    cols = {
        row_cid: terms_col(row_label, row_field, count_cid, size=row_size),
        pivot_cid: terms_col(pivot_label, pivot_field, count_cid, size=pivot_size),
        count_cid: count_col("Count"),
    }
    col_order = [row_cid, pivot_cid, count_cid]

    layer = make_layer(cols, col_order, lid)
    vis = datatable_vis(lid, col_order, count_cid,
                        transposed_cols={pivot_cid})

    return lens_obj(vis_id, title, "lnsDatatable", lid, layer, vis,
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
    Simplified dashboard with 4 sections:
      1. KPI metrics row
      2. Overview charts (timeline + type/severity distribution)
      3. Error analysis (error timeline + error details table)
      4. All events browser table
    """

    # ── 1. KPI ROW ───────────────────────────────────────────────────────────
    v_total    = build_metric(dv_id, "v_kpi_total", "Total Events",
                              subtitle="All events")
    v_errors   = build_metric(dv_id, "v_kpi_errors", "Total Errors",
                              base_filter=type_filter(ALL_ERROR_TYPES),
                              subtitle="Error events")
    v_sessions = build_metric(dv_id, "v_kpi_sessions", "Unique Sessions",
                              op="unique_count", source_field="sessionId",
                              subtitle="Distinct sessions")
    v_urls     = build_metric(dv_id, "v_kpi_urls", "Unique URLs",
                              op="unique_count", source_field="url",
                              subtitle="Distinct pages")
    v_high_sev = build_metric(dv_id, "v_kpi_high_sev", "High Severity",
                              base_filter=term_filter("severity", "high"),
                              subtitle="severity = high")
    v_critical = build_metric(dv_id, "v_kpi_critical", "Critical",
                              base_filter=term_filter("severity", "critical"),
                              subtitle="severity = critical")

    # ── 2. OVERVIEW ──────────────────────────────────────────────────────────
    v_timeline    = build_xy_time(dv_id, "v_timeline", "Events Over Time",
                                  series="bar_stacked")
    v_by_type     = build_pie(dv_id, "v_by_type", "Events by Type",
                              "type", shape="pie", size=20)
    v_by_severity = build_pie(dv_id, "v_by_severity", "Events by Severity",
                              "severity", shape="donut")

    v_app_timeline = build_xy_time_split(
        dv_id, "v_app_timeline", "Events by App Over Time",
        split_field="app", split_label="App",
        split_size=10, series="line",
        description="Line graph showing event count over time, one line per app")

    # ── 3. ERROR ANALYSIS ────────────────────────────────────────────────────
    v_error_ts    = build_xy_time(dv_id, "v_error_ts", "Errors Over Time",
                                  base_filter=type_filter(ALL_ERROR_TYPES),
                                  series="area")
    # ── 4. TABLES ────────────────────────────────────────────────────────────

    # Table 1: Pivot cross-tab — rows=App(domain), columns=Type, cells=Count
    v_pivot_table = build_pivot_datatable(
        dv_id, "v_pivot_table", "Events by App and Type",
        row_field="app", row_label="App",
        pivot_field="type", pivot_label="Type",
        pivot_size=25, row_size=50,
        description="Cross-tab: apps vs event types")

    # Table 2: Last 15 High Severity Events
    v_high_events = build_datatable(
        dv_id, "v_high_events", "Last 15 High Severity Events",
        [("App",      "terms", "app",       15),
         ("Severity", "terms", "severity",   5),
         ("Summary",  "terms", "summary",   15, False),
         ("Count",    "count", None)],
        sort_idx=-1,
        base_filter=term_filter("severity", "high"),
        description="Most recent high-severity events")

    # Table 3: Last 30 Events
    v_recent_events = build_datatable(
        dv_id, "v_recent_events", "Last 30 Events",
        [("App",      "terms", "app",       30),
         ("Type",     "terms", "type",      30),
         ("Summary",  "terms", "summary",   30, False),
         ("Severity", "terms", "severity",   5),
         ("Count",    "count", None)],
        sort_idx=-1,
        description="Most recent events across all types")

    # Table 4: Last 50 Events — App + Summary overview
    v_last50_events = build_datatable(
        dv_id, "v_last50_events", "Last 50 Events",
        [("App",     "terms", "app",     50),
         ("Summary", "terms", "summary", 50, False),
         ("Count",   "count", None)],
        sort_idx=-1,
        description="Last 50 events with app and summary")

    # ── LAYOUT ───────────────────────────────────────────────────────────────
    panels = [
        # KPI Row
        (v_total, 8, 8), (v_errors, 8, 8), (v_sessions, 8, 8),
        (v_urls, 8, 8), (v_high_sev, 8, 8), (v_critical, 8, 8),
        # Overview
        (v_timeline, 24, 14), (v_by_type, 12, 14), (v_by_severity, 12, 14),
        # App timeline
        (v_app_timeline, 48, 14),
        # Error Analysis
        (v_error_ts, 48, 12),
        # Tables
        (v_pivot_table, 48, 18),
        (v_high_events, 48, 16),
        (v_recent_events, 48, 20),
        (v_last50_events, 48, 22),
    ]

    all_vis = [p[0] for p in panels]
    dash = make_dashboard(
        "dashboard-main",
        "Selenium Monitoring Dashboard",
        "Event overview, error analysis, and full event browser.",
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
                "index.lifecycle.name": ILM_POLICY_NAME,
                "index.lifecycle.rollover_alias": ELASTIC_INDEX,
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
                    "reason":          {"type": "keyword"},
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
                    "app":               {"type": "keyword"},
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

    # ILM and rollover setup (order matters)
    create_ilm_policy()
    configure_field_mappings()
    migrate_existing_index()
    bootstrap_rollover_index()

    build_and_deploy()

    # Keep alive for docker
    while True:
        time.sleep(60)