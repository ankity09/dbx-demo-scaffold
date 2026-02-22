"""
Demo App — FastAPI assembly file.
Imports core modules, sets up lifespan, mounts health + chat + frontend.

Add your domain-specific routes below the marked section.
"""

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

from databricks.sdk import WorkspaceClient

from backend.core.lakebase import _init_pg_pool
from backend.core.health import health_router
from backend.core.streaming import stream_mas_chat
from backend.core import run_query, run_pg_query, _get_mas_auth

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

# ─── Chat history (in-memory, per-process) ────────────────────────────────
_chat_history: list[dict] = []

# ─── Action card config for your domain ───────────────────────────────────
# Override this list to detect entities created by the MAS agent during chat.
# Each entry maps a Lakebase table to an action card in the chat UI.
#
# ACTION_CARD_TABLES = [
#     {
#         "table": "work_orders",
#         "card_type": "work_order",
#         "id_col": "work_order_id",
#         "title_template": "Work Order {wo_number}",
#         "actions": ["approve", "dismiss"],
#         "detail_cols": {"asset": "asset_name", "priority": "priority", "status": "status"},
#     },
# ]
ACTION_CARD_TABLES: list[dict] = []


# ─── Lifespan ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):
    try:
        _init_pg_pool()
    except Exception as e:
        log.warning("Lakebase pool init deferred: %s", e)
    yield


app = FastAPI(title="Demo App", lifespan=lifespan)

# ─── Health endpoint ──────────────────────────────────────────────────────
app.include_router(health_router)


# ─── Chat endpoint (MAS streaming) ───────────────────────────────────────

@app.post("/api/chat")
async def chat(body: dict):
    """Streaming SSE endpoint for MAS chat."""
    message = body.get("message", "").strip()
    context = body.get("context", "").strip()
    if not message:
        raise HTTPException(400, "Empty message")

    full_message = f"Context: {context}\n\nQuestion: {message}" if context else message
    _chat_history.append({"role": "user", "content": full_message})

    async def event_stream():
        final_text = ""
        async for chunk in stream_mas_chat(message, _chat_history, ACTION_CARD_TABLES):
            yield chunk
            # Track final text for chat history
            if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                try:
                    evt = json.loads(chunk[6:])
                    if evt.get("type") == "delta":
                        final_text += evt.get("text", "")
                except (json.JSONDecodeError, KeyError):
                    pass
        if final_text:
            _chat_history.append({"role": "assistant", "content": final_text})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════════════
# Architecture (dynamic, auto-discovers MAS sub-agents)
# ═══════════════════════════════════════════════════════════════════════════

CATALOG = os.getenv("CATALOG", "")
SCHEMA = os.getenv("SCHEMA", "")
MAS_TILE_ID = os.getenv("MAS_TILE_ID", "")

w = WorkspaceClient()


def _slugify(s: str) -> str:
    """'F5 Support Data' → 'f5_support_data'"""
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _read_mas_config_from_disk() -> list[dict]:
    """Read agents[] from agent_bricks/mas_config.json as fallback."""
    try:
        config_path = Path(__file__).resolve().parent.parent.parent / "agent_bricks" / "mas_config.json"
        with open(config_path) as f:
            data = json.load(f)
        agents = data.get("agents", [])
        return [a for a in agents if not any(k.startswith("$") for k in a.keys())]
    except Exception as e:
        log.warning("Could not read MAS config from disk: %s", e)
        return []


async def _fetch_mas_agents() -> list[dict]:
    """Fetch MAS agents: live API first, disk fallback."""
    tile = MAS_TILE_ID
    if not tile:
        log.info("MAS_TILE_ID not set — using disk config for architecture")
        return _read_mas_config_from_disk()
    try:
        ep = await asyncio.to_thread(w.serving_endpoints.get, f"mas-{tile}-endpoint")
        full_uuid = ep.tile_endpoint_metadata.tile_id
        host, auth = await asyncio.to_thread(_get_mas_auth)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{host}/api/2.0/multi-agent-supervisors/{full_uuid}",
                headers={"Authorization": auth},
            )
            resp.raise_for_status()
            return resp.json().get("agents", [])
    except Exception as e:
        log.warning("Live MAS API failed (%s) — falling back to disk config", e)
        return _read_mas_config_from_disk()


def _build_infra_nodes(catalog: str, schema: str, delta_tables: list, lakebase_tables: list, status: str) -> list[dict]:
    """5 always-present scaffold infrastructure nodes."""
    return [
        {
            "key": "orchestrator", "name": "Demo Orchestrator", "type": "orchestrator",
            "status": status, "color": "#6366f1", "_layout_column": "left",
            "description": "End-to-end demo scaffold — provisions infrastructure, generates data, deploys AI agents, and serves the dashboard app.",
            "display_items": [
                {"text": f"Catalog: {catalog}", "status": "info"},
                {"text": f"Schema: {schema}", "status": "info"},
            ],
            "actions": ["Show me the full deployment sequence", "What infrastructure does this demo use?"],
            "details": {"catalog": catalog, "schema": schema}, "stats": [],
        },
        {
            "key": "schema_setup", "name": "Schema Setup", "type": "infrastructure",
            "status": status, "color": "#64748b", "_layout_column": "left",
            "description": "Notebook 01 — creates the Unity Catalog schema and grants for the demo.",
            "display_items": [
                {"text": f"Catalog: {catalog}", "status": "success"},
                {"text": f"Schema: {schema}", "status": "info"},
            ],
            "actions": ["What catalog and schema does this demo use?"],
            "details": {"catalog": catalog, "schema": schema}, "stats": [],
        },
        {
            "key": "data_generation", "name": "Data Generation", "type": "data-pipeline",
            "status": status, "color": "#10b981", "_layout_column": "left-data",
            "description": "Notebook 02 — generates realistic Delta Lake tables for the demo domain.",
            "display_items": [
                {"text": f"{len(delta_tables)} Delta tables created", "status": "success"},
                *[{"text": t["name"], "status": "info"} for t in delta_tables[:3]],
            ],
            "actions": ["What tables does the data generation create?"],
            "details": {"tables": [t["name"] for t in delta_tables]},
            "stats": [{"label": "tables", "value": len(delta_tables)}],
        },
        {
            "key": "lakebase_setup", "name": "Lakebase Setup", "type": "data-pipeline",
            "status": status, "color": "#f59e0b", "_layout_column": "left-data",
            "description": "Lakebase instance + database creation, core_schema.sql and domain_schema.sql applied, data seeded via notebook 03.",
            "display_items": [
                {"text": f"{len(lakebase_tables)} operational tables", "status": "success"},
                *[{"text": t, "status": "info"} for t in lakebase_tables[:2]],
            ],
            "actions": ["What tables are in Lakebase?"],
            "details": {"tables": lakebase_tables},
            "stats": [{"label": "tables", "value": len(lakebase_tables)}],
        },
        {
            "key": "app_dashboard", "name": "App / Dashboard", "type": "app",
            "status": status, "color": "#E4002B", "_layout_column": "app",
            "description": "FastAPI + single-file HTML frontend deployed as a Databricks App. Serves the dashboard, AI chat, and agent workflows.",
            "display_items": [
                {"text": "FastAPI backend", "status": "success"},
                {"text": "Databricks App deployment", "status": "info"},
            ],
            "actions": ["What pages does the dashboard have?", "How is the app deployed?"],
            "details": {}, "stats": [],
        },
    ]


def _build_agent_nodes(agents: list[dict], delta_tables: list, lakebase_tables: list) -> list[dict]:
    """Map MAS agents to architecture nodes dynamically."""
    nodes = []
    uc_functions = []

    # Normalize agent_type across disk (kebab-case) and live API (snake_case) formats
    TYPE_MAP = {
        "genie-space": "genie", "databricks_genie": "genie",
        "knowledge-assistant": "ka", "knowledge_assistant": "ka",
        "external-mcp-server": "mcp", "mcp_connection": "mcp",
        "unity-catalog-function": "uc", "unity_catalog_function": "uc",
        "serving-endpoint": "se", "serving_endpoint": "se",
    }
    COLOR_MAP = {"genie": "#3b82f6", "ka": "#8b5cf6", "mcp": "#f59e0b", "uc": "#06b6d4", "se": "#ec4899"}
    TYPE_NAME_MAP = {"genie": "genie-space", "ka": "serving-endpoint", "mcp": "mcp-server", "uc": "infrastructure", "se": "serving-endpoint"}

    for agent in agents:
        atype = agent.get("agent_type", "")
        category = TYPE_MAP.get(atype, "unknown")
        name = agent.get("name", "agent")
        desc = agent.get("description", "")
        slug = _slugify(name)

        if category == "uc":
            # Accumulate UC functions → collapse into 1 grouped node
            uc_path = agent.get("unity_catalog_function", {}).get("uc_path", {})
            fn_name = uc_path.get("name", name) if uc_path else name
            uc_functions.append({"name": fn_name, "description": desc})
            continue

        # Detect KA among serving-endpoint agents
        if category == "se":
            se_name = agent.get("serving_endpoint", {}).get("name", "")
            if "ka-" in se_name:
                category = "ka"

        node = {
            "key": f"{category}_{slug}",
            "name": name.replace("_", " ").replace("-", " ").title(),
            "type": TYPE_NAME_MAP.get(category, "mcp-server"),
            "status": "online",
            "color": COLOR_MAP.get(category, "#9ca3af"),
            "_layout_column": "middle",
            "description": desc,
            "display_items": [],
            "actions": [],
            "details": {},
            "stats": [],
        }

        if category == "genie":
            node["_feeds_from_delta"] = True
            genie_id = agent.get("genie_space", agent.get("databricks_genie", {})).get("id", agent.get("databricks_genie", {}).get("genie_space_id", ""))
            node["display_items"] = [
                {"text": f"{len(delta_tables)} tables connected", "status": "success"},
                *[{"text": t["name"], "status": "info"} for t in delta_tables[:2]],
            ]
            node["details"] = {"genie_space_id": genie_id, "tables": [t["name"] for t in delta_tables]}
            node["stats"] = [{"label": "tables", "value": len(delta_tables)}]
        elif category == "ka":
            node["display_items"] = [{"text": "Knowledge retrieval", "status": "success"}]
        elif category == "mcp":
            node["_feeds_from_lakebase"] = True
            node["display_items"] = [
                {"text": "16 MCP tools available", "status": "success"},
                {"text": f"{len(lakebase_tables)} operational tables", "status": "info"},
            ]
            node["details"] = {"tables": lakebase_tables}
            node["stats"] = [{"label": "MCP tools", "value": 16}, {"label": "tables", "value": len(lakebase_tables)}]

        nodes.append(node)

    # Collapse UC functions into 1 grouped node
    if uc_functions:
        fn_names = [f["name"] for f in uc_functions]
        nodes.append({
            "key": "uc_functions",
            "name": "UC Functions",
            "type": "infrastructure",
            "status": "online",
            "color": "#06b6d4",
            "_layout_column": "middle",
            "description": f"{len(uc_functions)} Unity Catalog function(s) for custom computations.",
            "display_items": [{"text": fn, "status": "info"} for fn in fn_names[:3]],
            "actions": [],
            "details": {"functions": fn_names},
            "stats": [{"label": "functions", "value": len(uc_functions)}],
        })

    return nodes


def _build_mas_node(agents: list[dict], mas_tile: str, status: str) -> dict:
    """Single MAS supervisor node."""
    return {
        "key": "mas", "name": "Multi-Agent Supervisor", "type": "mas",
        "status": status, "color": "#E4002B", "_layout_column": "right",
        "description": f"Orchestrates {len(agents)} specialized AI agents.",
        "display_items": [
            {"text": f"{len(agents)} sub-agents connected", "status": "success"},
            {"text": f"Endpoint: mas-{mas_tile}-endpoint", "status": "info"} if mas_tile else {"text": "Not yet configured", "status": "info"},
        ],
        "actions": [
            "What needs my attention right now?",
            "Show me the key metrics and trends.",
        ],
        "details": {"tile_id": mas_tile, "endpoint": f"mas-{mas_tile}-endpoint"} if mas_tile else {},
        "stats": [],
    }


def _compute_edges(nodes: list[dict]) -> list[dict]:
    """Derive edges from topology rules."""
    edges = []
    node_keys = {n["key"] for n in nodes}
    has_mas = "mas" in node_keys

    for n in nodes:
        # Sub-agents → MAS
        if has_mas and n.get("_layout_column") == "middle":
            edges.append({"source": n["key"], "target": "mas"})
        # Delta → Genie
        if n.get("_feeds_from_delta") and "data_generation" in node_keys:
            edges.append({"source": "data_generation", "target": n["key"]})
        # Lakebase → MCP
        if n.get("_feeds_from_lakebase") and "lakebase_setup" in node_keys:
            edges.append({"source": "lakebase_setup", "target": n["key"]})

    # Lakebase → App (always)
    if "lakebase_setup" in node_keys and "app_dashboard" in node_keys:
        edges.append({"source": "lakebase_setup", "target": "app_dashboard"})

    return edges


def _compute_layout(nodes: list[dict]) -> None:
    """Auto-assign x,y positions based on column assignments. Mutates in-place."""
    NODE_H = 180
    columns = {
        "left": {"x": 30, "nodes": []},
        "left-data": {"x": 400, "nodes": []},
        "middle": {"x": 770, "nodes": []},
        "middle-2": {"x": 1100, "nodes": []},
        "right": {"x": 1510, "nodes": []},
        "app": {"x": 1140, "nodes": []},
    }

    middle_nodes = []
    for n in nodes:
        col = n.get("_layout_column", "middle")
        if col == "middle":
            middle_nodes.append(n)
        elif col in columns:
            columns[col]["nodes"].append(n)

    # Split middle column if > 4 agents
    if len(middle_nodes) <= 4:
        columns["middle"]["nodes"] = middle_nodes
    else:
        half = (len(middle_nodes) + 1) // 2
        columns["middle"]["nodes"] = middle_nodes[:half]
        columns["middle-2"]["nodes"] = middle_nodes[half:]

    # Assign positions
    for col_key, col in columns.items():
        for i, n in enumerate(col["nodes"]):
            n["position"] = {"x": col["x"], "y": 30 + i * NODE_H}

    # Vertically center MAS node relative to the middle columns
    all_middle = columns["middle"]["nodes"] + columns["middle-2"]["nodes"]
    if columns["right"]["nodes"] and all_middle:
        mid_ys = [n["position"]["y"] for n in all_middle]
        center_y = (min(mid_ys) + max(mid_ys)) / 2
        for n in columns["right"]["nodes"]:
            n["position"] = {"x": columns["right"]["x"], "y": max(30, center_y)}

    # App node below MAS
    if columns["app"]["nodes"]:
        mas_y = columns["right"]["nodes"][0]["position"]["y"] if columns["right"]["nodes"] else 200
        for n in columns["app"]["nodes"]:
            n["position"] = {"x": columns["app"]["x"], "y": mas_y + NODE_H + 40}

    # Strip internal hints
    for n in nodes:
        n.pop("_layout_column", None)
        n.pop("_feeds_from_delta", None)
        n.pop("_feeds_from_lakebase", None)


@app.get("/api/architecture")
async def get_architecture():
    """Return live architecture metadata as flat nodes[] + edges[] for the DAG canvas."""
    catalog = CATALOG
    schema = SCHEMA

    async def _empty():
        return []

    # Parallel: DB queries + MAS discovery
    (q_tables, q_lb_tables, q_health, q_wf), agents = await asyncio.gather(
        asyncio.gather(
            asyncio.to_thread(run_query, f"SHOW TABLES IN {catalog}.{schema}") if catalog and schema else _empty(),
            asyncio.to_thread(run_pg_query, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"),
            asyncio.to_thread(run_query, "SELECT 1 as ok"),
            asyncio.to_thread(run_pg_query, "SELECT count(*) as cnt FROM workflows WHERE status = 'pending_approval'"),
        ),
        _fetch_mas_agents(),
    )

    workspace_url = os.getenv("DATABRICKS_HOST", "").rstrip("/")
    delta_tables = [{"name": t.get("tableName") or t.get("table_name", "")} for t in (q_tables or [])]
    lakebase_tables = [t["tablename"] for t in (q_lb_tables or [])]
    infra_status = "online" if q_health else "error"

    # Build nodes
    infra_nodes = _build_infra_nodes(catalog, schema, delta_tables, lakebase_tables, infra_status)
    agent_nodes = _build_agent_nodes(agents, delta_tables, lakebase_tables)
    all_nodes = infra_nodes + agent_nodes

    if agents:
        all_nodes.append(_build_mas_node(agents, MAS_TILE_ID, infra_status))

    # Compute edges + layout
    edges = _compute_edges(all_nodes)
    _compute_layout(all_nodes)

    return {
        "workspace_url": workspace_url,
        "nodes": all_nodes,
        "edges": edges,
        "live_stats": {
            "pending_workflows": (q_wf or [{}])[0].get("cnt", 0),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# --- Add your domain routes below ---
# ═══════════════════════════════════════════════════════════════════════════
#
# Example:
#   from backend.core import run_query, run_pg_query, write_pg, _safe
#
#   @app.get("/api/my-domain/metrics")
#   async def get_metrics():
#       return await asyncio.to_thread(run_query, "SELECT COUNT(*) as total FROM my_table")
#
#   @app.get("/api/my-domain/items")
#   async def get_items(status: str = None):
#       if status:
#           return await asyncio.to_thread(
#               run_pg_query,
#               "SELECT * FROM items WHERE status = %s ORDER BY created_at DESC",
#               (_safe(status),),
#           )
#       return await asyncio.to_thread(run_pg_query, "SELECT * FROM items ORDER BY created_at DESC")


# ─── Frontend Serving ─────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "frontend", "src")), name="static")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "index.html"))
