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
import uuid as _uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

from databricks.sdk import WorkspaceClient

from backend.core.lakebase import _init_pg_pool
from backend.core.health import health_router
from backend.core.streaming import stream_mas_chat, _sse_keepalive, get_mcp_pending, clear_mcp_pending
from backend.core import run_query, run_pg_query, write_pg, _safe, _get_mas_auth

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

# ─── Chat history (in-memory, per-process) ────────────────────────────────
_chat_history: list[dict] = []

# ─── Chat Persistence (Lakebase-backed session & message history) ─────────
# Requires chat_sessions and chat_messages tables (see lakebase/core_schema.sql).
# Falls back gracefully if tables don't exist yet.

_chat_session_id: str | None = None


def _ensure_chat_session() -> str:
    global _chat_session_id
    if _chat_session_id:
        return _chat_session_id
    try:
        rows = run_pg_query("SELECT session_id FROM chat_sessions ORDER BY updated_at DESC LIMIT 1")
        if rows:
            _chat_session_id = rows[0]["session_id"]
            return _chat_session_id
    except Exception:
        pass
    return _new_chat_session()


def _new_chat_session() -> str:
    global _chat_session_id
    sid = f"chat-{date.today().isoformat()}-{_uuid.uuid4().hex[:6]}"
    try:
        write_pg("INSERT INTO chat_sessions (session_id) VALUES (%s) ON CONFLICT DO NOTHING", (sid,))
    except Exception as e:
        log.warning("Could not create chat session: %s", e)
    _chat_session_id = sid
    return sid


def _save_chat_message(role: str, content: str):
    sid = _ensure_chat_session()
    try:
        write_pg(
            "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s)",
            (sid, role, content),
        )
        if role == "user":
            title = content[:100] + ("..." if len(content) > 100 else "")
            write_pg(
                "UPDATE chat_sessions SET updated_at = NOW(), title = COALESCE(NULLIF(title, 'New conversation'), %s) WHERE session_id = %s",
                (title, sid),
            )
        else:
            write_pg("UPDATE chat_sessions SET updated_at = NOW() WHERE session_id = %s", (sid,))
    except Exception as e:
        log.warning("Could not save chat message: %s", e)


def _load_chat_history() -> list[dict]:
    sid = _ensure_chat_session()
    try:
        rows = run_pg_query(
            "SELECT role, content FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC",
            (sid,),
        )
        return [{"role": r["role"], "content": r["content"]} for r in rows]
    except Exception:
        return []


def _clear_chat_history():
    global _chat_session_id
    if _chat_session_id:
        try:
            write_pg("DELETE FROM chat_sessions WHERE session_id = %s", (_chat_session_id,))
        except Exception:
            pass
    _chat_session_id = None

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
    # Hydrate in-memory chat history from Lakebase
    try:
        saved = _load_chat_history()
        if saved:
            _chat_history.extend(saved)
            log.info("Loaded %d messages from Lakebase chat history", len(saved))
    except Exception as e:
        log.warning("Could not load chat history: %s", e)
    yield


app = FastAPI(title="Demo App", lifespan=lifespan)

# ─── Health endpoint ──────────────────────────────────────────────────────
app.include_router(health_router)


# ─── Chat endpoint (MAS streaming) ───────────────────────────────────────

@app.post("/api/chat")
async def chat(request: Request, body: dict):
    """Streaming SSE endpoint for MAS chat with MCP approval flow.

    Normal message:   {"message": "Create a PO...", "auto_approve_mcp": true}
    MCP approval:     {"approve_mcp": true}  or  {"approve_mcp": false}
    """
    approve_mcp = body.get("approve_mcp", None)
    auto_approve_mcp = body.get("auto_approve_mcp", False)
    message = body.get("message", "").strip()
    context = body.get("context", "").strip()

    # Extract OBO token for MAS calls (required for MCP tools, auto-refreshes on expiry)
    user_token = request.headers.get("x-forwarded-access-token", "")

    # Determine starting state
    mcp_state = get_mcp_pending()
    if approve_mcp is not None and mcp_state:
        # Continuing from MCP approval — build input from saved state
        log.info("MCP APPROVAL received: approve=%s", approve_mcp)
        all_accumulated = mcp_state["accumulated"]
        tools_called = mcp_state["tools_called"]
        lakebase_called = mcp_state["lakebase_called"]
        approval_round = mcp_state["round"]

        for req in mcp_state["pending"]:
            all_accumulated.append({
                "type": "mcp_approval_response",
                "id": f"approval-{approval_round}-{req.get('id', '')}",
                "approval_request_id": req.get("id", ""),
                "approve": bool(approve_mcp),
            })
        start_messages = list(_chat_history[-10:]) + all_accumulated
        clear_mcp_pending()
    elif approve_mcp is not None and not mcp_state:
        # Stale approval — no pending state
        async def stale():
            yield f"data: {json.dumps({'type': 'error', 'text': 'No pending MCP approval.'})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(stale(), media_type="text/event-stream")
    else:
        # New user message
        if not message:
            raise HTTPException(400, "Empty message")
        full_message = f"Context: {context}\n\nQuestion: {message}" if context else message
        _chat_history.append({"role": "user", "content": full_message})
        try:
            _save_chat_message("user", full_message)
        except Exception:
            pass
        start_messages = list(_chat_history[-10:])
        all_accumulated = []
        tools_called = set()
        lakebase_called = False
        approval_round = 0

    async def event_stream():
        final_text = ""
        async for chunk in stream_mas_chat(
            message, _chat_history, ACTION_CARD_TABLES,
            user_token=user_token,
            auto_approve_mcp=auto_approve_mcp,
            start_messages=start_messages,
            initial_accumulated=all_accumulated,
            initial_tools_called=tools_called,
            initial_lakebase_called=lakebase_called,
            initial_approval_round=approval_round,
        ):
            yield chunk
            # Track final text for chat history
            if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                try:
                    evt = json.loads(chunk[6:])
                    if evt.get("type") == "delta":
                        final_text += evt.get("text", "")
                except (json.JSONDecodeError, KeyError):
                    pass
        # Save final response to chat history
        if final_text:
            _chat_history.append({"role": "assistant", "content": final_text})
            try:
                _save_chat_message("assistant", final_text)
            except Exception:
                pass

    return StreamingResponse(
        _sse_keepalive(event_stream()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ─── Chat History & Clear Endpoints ──────────────────────────────────────

@app.get("/api/chat/history")
async def get_chat_history():
    """Return all messages from the current chat session."""
    messages = await asyncio.to_thread(_load_chat_history)
    return {"session_id": _chat_session_id or "", "messages": messages}


@app.post("/api/chat/clear")
async def clear_chat():
    """Clear chat history (both in-memory and Lakebase)."""
    _chat_history.clear()
    await asyncio.to_thread(_clear_chat_history)
    return {"status": "cleared"}


# ═══════════════════════════════════════════════════════════════════════════
# Architecture (dynamic, auto-discovers MAS sub-agents)
# ═══════════════════════════════════════════════════════════════════════════

CATALOG = os.getenv("CATALOG", "")
SCHEMA = os.getenv("SCHEMA", "")
MAS_TILE_ID = os.getenv("MAS_TILE_ID", "")

w = WorkspaceClient()


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _load_demo_config() -> dict:
    """Load demo-config.yaml from the app directory (synced at deploy time)."""
    try:
        config_path = Path(__file__).resolve().parent.parent / "demo-config.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        log.warning("Could not read demo-config.yaml: %s", e)
        return {}


_DEMO_CONFIG: dict | None = None


def _get_demo_config() -> dict:
    global _DEMO_CONFIG
    if _DEMO_CONFIG is None:
        _DEMO_CONFIG = _load_demo_config()
    return _DEMO_CONFIG


def _agents_from_demo_config() -> list[dict]:
    """Convert ai_layer.sub_agents from demo-config.yaml into MAS agent format."""
    cfg = _get_demo_config()
    ai = cfg.get("ai_layer", {})
    sub_agents = ai.get("sub_agents", [])
    infra = cfg.get("infrastructure", {})
    catalog = infra.get("catalog", CATALOG)
    schema = infra.get("schema", SCHEMA)
    genie_space_id = os.getenv("GENIE_SPACE_ID", "")

    # Map demo-config.yaml types to MAS API kebab-case agent types.
    # MAS API requires kebab-case: genie-space, external-mcp-server, etc.
    TYPE_CONVERT = {
        "genie_space": "genie-space",
        "lakebase_mcp": "external-mcp-server",
        "knowledge_assistant": "knowledge-assistant",
        "unity_catalog_function": "unity-catalog-function",
    }

    agents = []
    for sa in sub_agents:
        sa_type = sa.get("type", "")
        agent_type = TYPE_CONVERT.get(sa_type, sa_type)
        name = sa.get("name", sa_type.replace("_", " ").title())
        desc = sa.get("description", "")

        agent: dict = {"agent_type": agent_type, "name": name, "description": desc}

        if agent_type == "genie-space":
            sa_genie_id = sa.get("genie_space_id", "") or genie_space_id
            agent["genie_space"] = {"id": sa_genie_id}
            if not agent.get("name") or agent["name"] == sa_type:
                agent["name"] = sa.get("name", "analytics_genie")
        elif agent_type == "external-mcp-server":
            agent["external_mcp_server"] = {"connection_name": sa.get("connection_name", sa.get("mcp_connection_id", ""))}
            if not agent.get("name") or agent["name"] == sa_type:
                agent["name"] = "lakebase_mcp"
        elif agent_type == "knowledge-assistant":
            ka_tile = os.getenv("KA_TILE_ID", "")
            agent["knowledge_assistant"] = {"knowledge_assistant_id": ka_tile} if ka_tile else {}
            if not agent.get("name") or agent["name"] == sa_type:
                agent["name"] = "knowledge_assistant"
        elif agent_type == "unity-catalog-function":
            agent["unity_catalog_function"] = {
                "uc_path": {"catalog": catalog, "schema": schema, "name": sa.get("function_name", "custom_function")}
            }
            if not agent.get("name") or agent["name"] == sa_type:
                agent["name"] = "uc_functions"

        agents.append(agent)

    return agents


def _read_mas_config_from_disk() -> list[dict]:
    """Read agents[] from agent_bricks/mas_config.json as fallback."""
    try:
        config_path = Path(__file__).resolve().parent.parent.parent / "agent_bricks" / "mas_config.json"
        with open(config_path) as f:
            data = json.load(f)
        agents = data.get("agents", [])
        # Strip $comment/$note keys but keep agents that have real keys
        return [
            {k: v for k, v in a.items() if not k.startswith("$")}
            for a in agents
            if not all(k.startswith("$") for k in a.keys())
        ]
    except Exception as e:
        log.warning("Could not read MAS config from disk: %s", e)
        return []


async def _fetch_mas_agents() -> list[dict]:
    """Fetch MAS agents: live API first, then demo-config, then mas_config.json fallback."""
    tile = MAS_TILE_ID
    if tile and tile != "TODO":
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
                agents = resp.json().get("agents", [])
                if agents:
                    return agents
        except Exception as e:
            log.warning("Live MAS API failed (%s) — trying demo-config fallback", e)

    agents = _agents_from_demo_config()
    if agents:
        log.info("Using demo-config.yaml for architecture (%d agents)", len(agents))
        return agents

    agents = _read_mas_config_from_disk()
    if agents:
        log.info("Using mas_config.json for architecture (%d agents)", len(agents))
        return agents

    log.warning("No agent definitions found — architecture will show data + app nodes only")
    return []


def _build_data_nodes(
    catalog: str, schema: str, workspace_url: str,
    delta_tables: list[dict], delta_row_counts: dict,
    lakebase_tables: list[str], lakebase_row_counts: dict,
) -> list[dict]:
    """Two data-source nodes: Delta Lake (analytics) and Lakebase (operational)."""
    nodes = []
    dt_items = [{"text": f"{len(delta_tables)} tables", "status": "success"}]
    for t in delta_tables[:4]:
        name = t.get("name", "")
        cnt = delta_row_counts.get(name, "")
        label = f"{name}  ({cnt:,} rows)" if isinstance(cnt, int) else name
        dt_items.append({"text": label, "status": "info"})
    total_delta_rows = sum(v for v in delta_row_counts.values() if isinstance(v, int))
    nodes.append({
        "key": "lakehouse", "name": "Lakehouse", "type": "lakehouse-node",
        "status": "online", "color": "#3b82f6", "_layout_column": "data-sources",
        "type_badge": "LAKEHOUSE",
        "description": f"Unity Catalog tables in {catalog}.{schema} — analytical data powering Genie queries, UC Functions, and dashboards.",
        "display_items": dt_items,
        "actions": [],
        "details": {"tables": [t.get("name", "") for t in delta_tables], "row_counts": delta_row_counts},
        "stats": [{"label": "tables", "value": len(delta_tables)}, {"label": "rows", "value": total_delta_rows}],
        "workspace_url": f"{workspace_url}/explore/data/{catalog}/{schema}" if workspace_url else "",
    })
    lb_items = [{"text": f"{len(lakebase_tables)} operational tables", "status": "success"}]
    for t in lakebase_tables[:4]:
        cnt = lakebase_row_counts.get(t, "")
        label = f"{t}  ({cnt:,} rows)" if isinstance(cnt, int) else t
        lb_items.append({"text": label, "status": "info"})
    total_lb_rows = sum(v for v in lakebase_row_counts.values() if isinstance(v, int))
    nodes.append({
        "key": "lakebase", "name": "Lakebase (Operational)", "type": "lakebase",
        "status": "online", "color": "#f59e0b", "_layout_column": "data-sources",
        "type_badge": "LAKEBASE",
        "description": "Postgres-compatible operational database for real-time state management, workflows, and agent actions.",
        "display_items": lb_items,
        "actions": [],
        "details": {"tables": lakebase_tables, "row_counts": lakebase_row_counts},
        "stats": [{"label": "tables", "value": len(lakebase_tables)}, {"label": "rows", "value": total_lb_rows}],
        "workspace_url": f"{workspace_url}/sql/databases" if workspace_url else "",
    })
    return nodes


def _build_app_node(
    workspace_url: str, demo_name: str, active_cases: int, pending_wf: int,
    lakebase_tables: list[str],
) -> dict:
    app_url = os.getenv("DATABRICKS_APP_URL", "")
    items = [
        {"text": "FastAPI + Vanilla JS", "status": "success"},
    ]
    if active_cases:
        items.append({"text": f"{active_cases} active records", "status": "info"})
    if pending_wf:
        items.append({"text": f"{pending_wf} pending workflows", "status": "info"})
    return {
        "key": "app", "name": demo_name or "Demo Application", "type": "app",
        "status": "online", "color": "#E4002B", "_layout_column": "application",
        "type_badge": "APPLICATION",
        "description": "Databricks App serving the dashboard, AI chat, agent workflows, and domain pages.",
        "display_items": items,
        "actions": [],
        "details": {"app_url": app_url},
        "stats": [{"label": "pending", "value": pending_wf}],
        "workspace_url": f"{workspace_url}/apps" if workspace_url else app_url,
    }


def _build_agent_nodes(
    agents: list[dict], workspace_url: str,
    delta_tables: list[dict], delta_row_counts: dict,
    lakebase_tables: list[str], lakebase_row_counts: dict,
    genie_space_id_env: str = "",
) -> list[dict]:
    """Map MAS agents to architecture nodes dynamically."""
    nodes = []
    uc_functions = []

    TYPE_MAP = {
        "genie-space": "genie", "databricks_genie": "genie",
        "knowledge-assistant": "ka", "knowledge_assistant": "ka",
        "external-mcp-server": "mcp", "mcp_connection": "mcp",
        "unity-catalog-function": "uc", "unity_catalog_function": "uc",
        "serving-endpoint": "se", "serving_endpoint": "se",
    }
    COLOR_MAP = {"genie": "#3b82f6", "ka": "#8b5cf6", "mcp": "#f59e0b", "uc": "#06b6d4", "se": "#ec4899"}
    BADGE_MAP = {"genie": "GENIE SPACE", "ka": "KNOWLEDGE ASSISTANT", "mcp": "MCP SERVER", "uc": "UC FUNCTIONS", "se": "SERVING ENDPOINT"}
    TYPE_NAME_MAP = {"genie": "genie-space", "ka": "serving-endpoint", "mcp": "mcp-server", "uc": "infrastructure", "se": "serving-endpoint"}

    for agent in agents:
        atype = agent.get("agent_type", "")
        category = TYPE_MAP.get(atype, "unknown")
        name = agent.get("name", "agent")
        desc = agent.get("description", "")
        slug = _slugify(name)

        if category == "uc":
            uc_path = agent.get("unity_catalog_function", {}).get("uc_path", {})
            fn_name = uc_path.get("name", name) if uc_path else name
            uc_functions.append({"name": fn_name, "description": desc})
            continue

        if category == "se":
            se_name = agent.get("serving_endpoint", {}).get("name", "")
            if "ka-" in se_name or "knowledge" in name.lower():
                category = "ka"

        node = {
            "key": f"{category}_{slug}",
            "name": name.replace("_", " ").replace("-", " ").title(),
            "type": TYPE_NAME_MAP.get(category, "mcp-server"),
            "status": "online", "color": COLOR_MAP.get(category, "#9ca3af"),
            "_layout_column": "agents",
            "type_badge": BADGE_MAP.get(category, "AGENT"),
            "description": desc, "display_items": [], "actions": [], "details": {}, "stats": [],
            "workspace_url": "",
        }

        if category == "genie":
            node["_feeds_from_delta"] = True
            genie_id = agent.get("genie_space", agent.get("databricks_genie", {})).get("id", agent.get("databricks_genie", {}).get("genie_space_id", ""))
            genie_id = genie_id or genie_space_id_env
            connected_tables = [t.get("name", "") for t in delta_tables]
            items = [{"text": f"{len(delta_tables)} Delta tables connected", "status": "success"}]
            for t in delta_tables[:3]:
                tname = t.get("name", "")
                cnt = delta_row_counts.get(tname, "")
                label = f"{tname}  ({cnt:,} rows)" if isinstance(cnt, int) else tname
                items.append({"text": label, "status": "info"})
            node["display_items"] = items
            node["details"] = {"genie_space_id": genie_id, "tables": connected_tables}
            node["stats"] = [{"label": "tables", "value": len(delta_tables)}]
            node["workspace_url"] = f"{workspace_url}/genie/rooms/{genie_id}" if workspace_url and genie_id else ""
        elif category == "ka":
            node["_feeds_from_delta"] = True
            ka_id = ""
            se_cfg = agent.get("serving_endpoint", {})
            if se_cfg:
                ka_id = se_cfg.get("name", "").replace("ka-", "").replace("-endpoint", "")
            node["display_items"] = [
                {"text": "Knowledge retrieval", "status": "success"},
                {"text": "Searches KB articles + documentation", "status": "info"},
            ]
            node["workspace_url"] = f"{workspace_url}/ml/bricks/ka/configure/{ka_id}" if workspace_url and ka_id else ""
        elif category == "mcp":
            node["_feeds_from_lakebase"] = True
            node["display_items"] = [
                {"text": "16 MCP tools available", "status": "success"},
                {"text": f"{len(lakebase_tables)} operational tables", "status": "info"},
                {"text": "READ, WRITE, SQL, DDL", "status": "info"},
            ]
            node["details"] = {"tables": lakebase_tables}
            node["stats"] = [{"label": "MCP tools", "value": 16}, {"label": "tables", "value": len(lakebase_tables)}]

        nodes.append(node)

    if uc_functions:
        fn_names = [f["name"] for f in uc_functions]
        fn_items = []
        for f in uc_functions[:8]:
            label = f["name"]
            if f.get("description"):
                label += f" — {f['description'][:40]}"
            fn_items.append({"text": label, "status": "info"})
        if len(uc_functions) > 8:
            fn_items.append({"text": f"+ {len(uc_functions) - 8} more functions", "status": "info"})
        nodes.append({
            "key": "uc_functions", "name": "UC Functions", "type": "infrastructure",
            "status": "online", "color": "#06b6d4", "_layout_column": "agents",
            "_feeds_from_delta": True,
            "type_badge": "UC FUNCTIONS",
            "description": f"{len(uc_functions)} Unity Catalog function(s) for custom computations.",
            "display_items": fn_items,
            "actions": [], "details": {"functions": fn_names},
            "stats": [{"label": "functions", "value": len(uc_functions)}],
            "workspace_url": f"{workspace_url}/explore/data/{CATALOG}/{SCHEMA}" if workspace_url else "",
        })

    return nodes


def _build_mas_node(agents: list[dict], mas_tile: str, workspace_url: str, status: str, pending_wf: int = 0) -> dict:
    items = [
        {"text": f"{len(agents)} sub-agents connected", "status": "success"},
    ]
    for a in agents:
        aname = a.get("name", "").replace("_", " ").title()
        if aname:
            items.append({"text": aname, "status": "info"})
    if mas_tile:
        items.append({"text": f"Endpoint: mas-{mas_tile}-endpoint", "status": "info"})
    if pending_wf:
        items.append({"text": f"{pending_wf} pending workflows", "status": "info"})
    return {
        "key": "mas", "name": "Multi-Agent Supervisor", "type": "mas",
        "status": status, "color": "#E4002B", "_layout_column": "orchestration",
        "type_badge": "MAS",
        "description": f"Orchestrates {len(agents)} specialized AI agents. Routes user queries to the best agent, manages context, and coordinates multi-step workflows.",
        "display_items": items,
        "actions": [],
        "details": {
            "tile_id": mas_tile,
            "endpoint": f"mas-{mas_tile}-endpoint",
            "sub_agent_names": [a.get("name", "").replace("_", " ").title() for a in agents],
        } if mas_tile else {"sub_agent_names": [a.get("name", "").replace("_", " ").title() for a in agents]},
        "stats": [{"label": "sub-agents", "value": len(agents)}],
        "workspace_url": f"{workspace_url}/ml/bricks/mas/configure/{mas_tile}" if workspace_url and mas_tile else "",
    }


def _compute_edges(nodes: list[dict]) -> list[dict]:
    edges = []
    node_keys = {n["key"] for n in nodes}
    has_mas = "mas" in node_keys
    has_app = "app" in node_keys

    for n in nodes:
        if has_mas and n.get("_layout_column") == "agents":
            edges.append({"source": n["key"], "target": "mas", "color": "#9ca3af"})
        if n.get("_feeds_from_delta") and "lakehouse" in node_keys:
            edges.append({"source": "lakehouse", "target": n["key"], "color": "#3b82f6"})
        if n.get("_feeds_from_lakebase") and "lakebase" in node_keys:
            edges.append({"source": "lakebase", "target": n["key"], "color": "#f59e0b"})

    if has_mas and has_app:
        edges.append({"source": "mas", "target": "app", "color": "#E4002B"})
    if "lakebase" in node_keys and has_app:
        edges.append({"source": "lakebase", "target": "app", "color": "#f59e0b"})

    return edges


def _compute_layout(nodes: list[dict]) -> None:
    AGENT_GAP = 140
    COL_X = {"data-sources": 100, "agents": 450, "orchestration": 930, "application": 1250}

    data_nodes = [n for n in nodes if n.get("_layout_column") == "data-sources"]
    agent_nodes = [n for n in nodes if n.get("_layout_column") == "agents"]
    orch_nodes = [n for n in nodes if n.get("_layout_column") == "orchestration"]
    app_nodes = [n for n in nodes if n.get("_layout_column") == "application"]

    agent_nodes.sort(key=lambda n: (1 if n.get("_feeds_from_lakebase") and not n.get("_feeds_from_delta") else 0))

    agent_start_y = 30
    for i, n in enumerate(agent_nodes):
        n["position"] = {"x": COL_X["agents"], "y": agent_start_y + i * AGENT_GAP}
    agent_bottom = agent_start_y + max(0, len(agent_nodes) - 1) * AGENT_GAP

    lakehouse = [n for n in data_nodes if n["key"] == "lakehouse"]
    lakebase = [n for n in data_nodes if n["key"] == "lakebase"]

    if lakehouse:
        lakehouse[0]["position"] = {"x": COL_X["data-sources"], "y": agent_start_y}
    if lakebase:
        lakebase[0]["position"] = {"x": COL_X["data-sources"], "y": agent_bottom + AGENT_GAP}

    for i, n in enumerate(orch_nodes):
        n["position"] = {"x": COL_X["orchestration"], "y": agent_start_y + i * AGENT_GAP}

    agent_center_y = agent_start_y + (agent_bottom - agent_start_y) / 2
    for i, n in enumerate(app_nodes):
        n["position"] = {"x": COL_X["application"], "y": max(agent_center_y - 20, agent_start_y) + i * AGENT_GAP}

    for n in nodes:
        n.pop("_layout_column", None)
        n.pop("_feeds_from_delta", None)
        n.pop("_feeds_from_lakebase", None)


@app.get("/api/architecture")
async def get_architecture():
    """Return live architecture metadata as flat nodes[] + edges[] for the DAG canvas."""
    catalog = CATALOG
    schema = SCHEMA
    demo_name = os.getenv("DEMO_NAME", "")
    demo_customer = os.getenv("DEMO_CUSTOMER", "")
    genie_space_id = os.getenv("GENIE_SPACE_ID", "")
    _cfg = _get_demo_config()
    workspace_url = _cfg.get("infrastructure", {}).get("workspace_url", "").rstrip("/")
    if not workspace_url:
        workspace_url = os.getenv("DATABRICKS_HOST", "").rstrip("/")

    async def _empty():
        return []

    (q_tables, q_lb_tables, q_health, q_cases, q_wf, q_lb_counts), agents = await asyncio.gather(
        asyncio.gather(
            asyncio.to_thread(run_query, f"SHOW TABLES IN {catalog}.{schema}") if catalog and schema else _empty(),
            asyncio.to_thread(run_pg_query, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"),
            asyncio.to_thread(run_query, "SELECT 1 as ok"),
            _empty(),  # placeholder — override with domain active-record count if needed
            asyncio.to_thread(run_pg_query, "SELECT count(*) as cnt FROM workflows WHERE status = 'pending_approval'"),
            asyncio.to_thread(run_pg_query, "SELECT relname, n_live_tup FROM pg_stat_user_tables"),
        ),
        _fetch_mas_agents(),
    )

    delta_tables = [{"name": t.get("tableName") or t.get("table_name", "")} for t in (q_tables or [])]
    lakebase_tables = [t["tablename"] for t in (q_lb_tables or [])]
    infra_status = "online" if q_health else "error"
    active_cases = 0
    try:
        active_cases = (q_cases or [{}])[0].get("cnt", 0)
    except Exception:
        pass
    pending_wf = (q_wf or [{}])[0].get("cnt", 0)

    lakebase_row_counts = {}
    for row in (q_lb_counts or []):
        lakebase_row_counts[row.get("relname", "")] = int(row.get("n_live_tup", 0))

    delta_row_counts = {}
    if delta_tables and catalog and schema:
        async def _count_delta(tname):
            try:
                r = await asyncio.to_thread(run_query, f"SELECT COUNT(*) as cnt FROM {catalog}.{schema}.{tname}")
                return tname, int((r or [{}])[0].get("cnt", 0))
            except Exception:
                return tname, "?"
        results = await asyncio.gather(*[_count_delta(t["name"]) for t in delta_tables])
        delta_row_counts = dict(results)

    # ── Rich metadata: table schemas, genie details, function signatures ──
    delta_schemas = {}
    lakebase_schemas = {}

    async def _describe_delta(tname):
        try:
            r = await asyncio.to_thread(run_query, f"DESCRIBE TABLE {catalog}.{schema}.{tname}")
            cols = [{"col": row.get("col_name", ""), "type": row.get("data_type", "")} for row in (r or []) if row.get("col_name") and not row.get("col_name", "").startswith("#")]
            return tname, cols
        except Exception:
            return tname, []

    async def _describe_lakebase_all():
        try:
            r = await asyncio.to_thread(
                run_pg_query,
                "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = 'public' ORDER BY table_name, ordinal_position",
            )
            schemas = {}
            for row in (r or []):
                tbl = row.get("table_name", "")
                if tbl not in schemas:
                    schemas[tbl] = []
                schemas[tbl].append({"col": row.get("column_name", ""), "type": row.get("data_type", "")})
            return schemas
        except Exception:
            return {}

    async def _describe_genie(genie_id):
        if not genie_id:
            return {}
        try:
            host_val = workspace_url or os.getenv("DATABRICKS_HOST", "").rstrip("/")
            token = os.getenv("DATABRICKS_TOKEN", "")
            if not token:
                _h, _a = await asyncio.to_thread(_get_mas_auth)
                auth_header = _a
            else:
                auth_header = f"Bearer {token}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{host_val}/api/2.0/data-rooms/{genie_id}",
                    headers={"Authorization": auth_header},
                )
                resp.raise_for_status()
                d = resp.json()
                return {
                    "name": d.get("display_name", d.get("name", "")),
                    "description": d.get("description", ""),
                    "table_count": len(d.get("table_identifiers", [])),
                    "tables": [t.get("table_identifier", "") for t in d.get("table_identifiers", [])[:10]],
                    "instructions_snippet": (d.get("curated_questions") or [{}])[0].get("question", "") if d.get("curated_questions") else "",
                }
        except Exception as e:
            log.warning("Genie describe failed for %s: %s", genie_id, e)
            return {}

    async def _describe_ka_endpoint(endpoint_name):
        if not endpoint_name:
            return {}
        try:
            ep = await asyncio.to_thread(w.serving_endpoints.get, endpoint_name)
            state = "READY" if ep.state and ep.state.ready == "READY" else "NOT_READY"
            return {"endpoint_name": endpoint_name, "state": state}
        except Exception as e:
            log.warning("KA endpoint describe failed for %s: %s", endpoint_name, e)
            return {}

    async def _describe_ka(ka_id):
        if not ka_id:
            return {}
        try:
            host_val = os.getenv("DATABRICKS_HOST", "").rstrip("/")
            auth_header = _get_mas_auth()[1]  # reuse auth helper
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{host_val}/api/2.0/knowledge-assistants/{ka_id}",
                    headers={"Authorization": auth_header},
                )
                resp.raise_for_status()
                d = resp.json()
                return {
                    "name": d.get("display_name", d.get("name", "")),
                    "description": d.get("description", ""),
                    "index_count": len(d.get("vector_search_indexes", d.get("indexes", []))),
                    "indexes": [idx.get("name", idx.get("index_name", "")) for idx in d.get("vector_search_indexes", d.get("indexes", []))[:5]],
                    "endpoint_name": d.get("endpoint_name", d.get("serving_endpoint_name", "")),
                }
        except Exception as e:
            log.warning("KA describe failed for %s: %s", ka_id, e)
            return {}

    async def _describe_uc_fn(fn_catalog, fn_schema, fn_name):
        try:
            r = await asyncio.to_thread(run_query, f"DESCRIBE FUNCTION {fn_catalog}.{fn_schema}.{fn_name}")
            info = {}
            for row in (r or []):
                key = row.get("info_name", row.get("function_desc", ""))
                val = row.get("info_value", row.get("function_desc", ""))
                if key:
                    info[key.lower().replace(" ", "_")] = val
            return fn_name, info
        except Exception:
            return fn_name, {}

    describe_tasks = []
    for t in delta_tables:
        describe_tasks.append(_describe_delta(t["name"]))
    describe_tasks.append(_describe_lakebase_all())

    genie_ids = []
    ka_endpoints = []
    ka_ids = []
    uc_fn_specs = []
    for ag in agents:
        atype = ag.get("agent_type", "")
        if atype in ("databricks_genie", "genie-space"):
            gid = ag.get("databricks_genie", ag.get("genie_space", {})).get("genie_space_id", ag.get("genie_space", ag.get("databricks_genie", {})).get("id", ""))
            gid = gid or genie_space_id
            if gid:
                genie_ids.append(gid)
                describe_tasks.append(_describe_genie(gid))
        elif atype in ("serving_endpoint", "knowledge_assistant"):
            ep_name = ag.get("serving_endpoint", {}).get("name", "")
            if ep_name and "ka-" in ep_name:
                ka_endpoints.append(ep_name)
                describe_tasks.append(_describe_ka_endpoint(ep_name))
            # Also try to get full KA details via KA API
            ka_id = ag.get("knowledge_assistant", {}).get("ka_id", "")
            if not ka_id and ep_name:
                ka_id = ep_name.replace("ka-", "").replace("-endpoint", "")
            if ka_id:
                ka_ids.append(ka_id)
                describe_tasks.append(_describe_ka(ka_id))
        elif atype == "unity_catalog_function":
            uc_path = ag.get("unity_catalog_function", {}).get("uc_path", {})
            if uc_path:
                fn_c = uc_path.get("catalog", catalog)
                fn_s = uc_path.get("schema", schema)
                fn_n = uc_path.get("name", "")
                if fn_n:
                    uc_fn_specs.append(fn_n)
                    describe_tasks.append(_describe_uc_fn(fn_c, fn_s, fn_n))

    describe_results = await asyncio.gather(*describe_tasks, return_exceptions=True)

    idx = 0
    for t in delta_tables:
        r = describe_results[idx]
        if not isinstance(r, Exception):
            name, cols = r
            delta_schemas[name] = cols
        idx += 1
    r = describe_results[idx]
    if not isinstance(r, Exception):
        lakebase_schemas = r
    idx += 1
    genie_details = {}
    for gid in genie_ids:
        r = describe_results[idx]
        if not isinstance(r, Exception):
            genie_details[gid] = r
        idx += 1
    ka_details = {}
    for ep in ka_endpoints:
        r = describe_results[idx]
        if not isinstance(r, Exception):
            ka_details[ep] = r
        idx += 1
    # KA full details (from KA API)
    ka_full_details = {}
    for kid in ka_ids:
        r = describe_results[idx]
        if not isinstance(r, Exception):
            ka_full_details[kid] = r
        idx += 1
    uc_fn_details = {}
    for fn in uc_fn_specs:
        r = describe_results[idx]
        if not isinstance(r, Exception):
            fname, info = r
            uc_fn_details[fname] = info
        idx += 1

    # Build nodes
    data_nodes = _build_data_nodes(
        catalog, schema, workspace_url,
        delta_tables, delta_row_counts,
        lakebase_tables, lakebase_row_counts,
    )
    for n in data_nodes:
        if n["key"] == "lakehouse":
            n["details"]["table_schemas"] = delta_schemas
        elif n["key"] == "lakebase":
            n["details"]["table_schemas"] = lakebase_schemas

    agent_nodes = _build_agent_nodes(
        agents, workspace_url,
        delta_tables, delta_row_counts,
        lakebase_tables, lakebase_row_counts,
        genie_space_id_env=genie_space_id,
    )
    for n in agent_nodes:
        if n["type"] == "genie-space":
            gid = n.get("details", {}).get("genie_space_id", "")
            if gid and gid in genie_details:
                gd = genie_details[gid]
                n["details"]["genie_name"] = gd.get("name", "")
                n["details"]["genie_description"] = gd.get("description", "")
                n["details"]["genie_table_count"] = gd.get("table_count", 0)
                n["details"]["genie_tables"] = gd.get("tables", [])
                n["details"]["curated_question"] = gd.get("instructions_snippet", "")
                if gd.get("name"):
                    n["name"] = gd["name"]
        elif n.get("type") == "serving-endpoint" and n.get("type_badge") in ("KNOWLEDGE ASSISTANT", "SERVING ENDPOINT"):
            for ep, kd in ka_details.items():
                if ep in str(n.get("details", {})) or ep in str(n.get("workspace_url", "")):
                    n["details"]["endpoint_state"] = kd.get("state", "")
                    if kd.get("state") == "READY":
                        n["display_items"].append({"text": "Endpoint READY", "status": "success"})
                    break
            # Enrich with full KA API details
            for kid, kfull in ka_full_details.items():
                if kid in str(n.get("workspace_url", "")) or kid in str(n.get("details", {})):
                    if kfull.get("name"):
                        n["name"] = kfull["name"]
                    if kfull.get("description"):
                        n["details"]["ka_description"] = kfull["description"]
                    if kfull.get("indexes"):
                        n["details"]["ka_indexes"] = kfull["indexes"]
                        n["details"]["ka_index_count"] = kfull.get("index_count", 0)
                    if kfull.get("endpoint_name"):
                        n["details"]["ka_endpoint"] = kfull["endpoint_name"]
                    break
        elif n.get("key") == "uc_functions":
            n["details"]["function_details"] = uc_fn_details

    all_nodes = data_nodes + agent_nodes

    if agents:
        mas_node = _build_mas_node(agents, MAS_TILE_ID, workspace_url, infra_status, pending_wf)
        cfg = _get_demo_config()
        mas_persona = cfg.get("ai_layer", {}).get("mas_persona", "")
        if mas_persona:
            mas_node["details"]["instructions"] = mas_persona
        all_nodes.append(mas_node)

    all_nodes.append(_build_app_node(workspace_url, demo_name, active_cases, pending_wf, lakebase_tables))

    edges = _compute_edges(all_nodes)
    _compute_layout(all_nodes)

    return {
        "workspace_url": workspace_url,
        "demo_name": demo_name,
        "demo_customer": demo_customer,
        "column_labels": [
            {"key": "data-sources", "label": "DATA SOURCES", "x": 100},
            {"key": "agents", "label": "AI AGENTS", "x": 450},
            {"key": "orchestration", "label": "ORCHESTRATION", "x": 930},
            {"key": "application", "label": "APPLICATION", "x": 1250},
        ],
        "nodes": all_nodes,
        "edges": edges,
        "live_stats": {
            "active_cases": active_cases,
            "pending_workflows": pending_wf,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Architecture: Table Data Explorer
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/architecture/table-data")
async def get_architecture_table_data(
    table: str = Query(..., min_length=1, max_length=128),
    source: str = Query(..., pattern=r"^(delta|lakebase)$"),
    limit: int = Query(20, ge=1, le=100),
):
    """Return schema + sample rows for a single table (used by the data explorer)."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
        raise HTTPException(400, "Invalid table name")

    catalog = CATALOG
    schema = SCHEMA

    if source == "delta":
        known = await asyncio.to_thread(
            run_query, f"SHOW TABLES IN {catalog}.{schema}"
        )
        known_names = {t.get("tableName") or t.get("table_name", "") for t in (known or [])}
        if table not in known_names:
            raise HTTPException(404, f"Table '{table}' not found in {catalog}.{schema}")

        fqn = f"{catalog}.{schema}.{table}"
        q_rows, q_desc, q_count = await asyncio.gather(
            asyncio.to_thread(run_query, f"SELECT * FROM {fqn} LIMIT {limit}"),
            asyncio.to_thread(run_query, f"DESCRIBE TABLE {fqn}"),
            asyncio.to_thread(run_query, f"SELECT COUNT(*) as cnt FROM {fqn}"),
        )
        columns = [
            {"col": r.get("col_name", ""), "type": r.get("data_type", "")}
            for r in (q_desc or [])
            if r.get("col_name") and not r.get("col_name", "").startswith("#")
        ]
        return {
            "table": table,
            "source": "delta",
            "columns": columns,
            "rows": q_rows or [],
            "row_count": int((q_count or [{}])[0].get("cnt", 0)),
        }

    else:  # lakebase
        known = await asyncio.to_thread(
            run_pg_query,
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'",
        )
        known_names = {t["tablename"] for t in (known or [])}
        if table not in known_names:
            raise HTTPException(404, f"Table '{table}' not found in Lakebase")

        q_rows, q_schema, q_count = await asyncio.gather(
            asyncio.to_thread(
                run_pg_query,
                f"SELECT * FROM {table} LIMIT %s",
                (limit,),
            ),
            asyncio.to_thread(
                run_pg_query,
                """SELECT c.column_name, c.data_type, c.is_nullable, c.column_default,
                          CASE WHEN kcu.column_name IS NOT NULL THEN 'PK' ELSE NULL END as key
                   FROM information_schema.columns c
                   LEFT JOIN information_schema.key_column_usage kcu
                     ON kcu.table_name = c.table_name AND kcu.column_name = c.column_name
                     AND kcu.table_schema = c.table_schema
                   WHERE c.table_schema = 'public' AND c.table_name = %s
                   ORDER BY c.ordinal_position""",
                (table,),
            ),
            asyncio.to_thread(
                run_pg_query,
                "SELECT n_live_tup as cnt FROM pg_stat_user_tables WHERE relname = %s",
                (table,),
            ),
        )
        columns = [
            {
                "col": r.get("column_name", ""),
                "type": r.get("data_type", ""),
                "nullable": r.get("is_nullable", "YES") == "YES",
                "default": r.get("column_default"),
                "key": r.get("key"),
            }
            for r in (q_schema or [])
        ]
        return {
            "table": table,
            "source": "lakebase",
            "columns": columns,
            "rows": q_rows or [],
            "row_count": int((q_count or [{}])[0].get("cnt", 0)),
        }


# ═══════════════════════════════════════════════════════════════════════════
# Agent Workflows — powers the Agent Workflows page
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/agent-overview")
async def get_agent_overview():
    """Return KPIs, workflows, and recent agent actions for the Agent page."""
    try:
        q_pending, q_in_progress, q_completed_7d, q_actions_24h, q_workflows, q_actions = await asyncio.gather(
            asyncio.to_thread(run_pg_query, "SELECT count(*) as cnt FROM workflows WHERE status = 'pending_approval'"),
            asyncio.to_thread(run_pg_query, "SELECT count(*) as cnt FROM workflows WHERE status = 'in_progress'"),
            asyncio.to_thread(run_pg_query, "SELECT count(*) as cnt FROM workflows WHERE status = 'approved' AND completed_at >= NOW() - INTERVAL '7 days'"),
            asyncio.to_thread(run_pg_query, "SELECT count(*) as cnt FROM agent_actions WHERE created_at >= NOW() - INTERVAL '24 hours'"),
            asyncio.to_thread(run_pg_query, "SELECT * FROM workflows ORDER BY created_at DESC LIMIT 50"),
            asyncio.to_thread(run_pg_query, "SELECT * FROM agent_actions ORDER BY created_at DESC LIMIT 20"),
        )
        return {
            "kpis": {
                "pending_approval": (q_pending or [{}])[0].get("cnt", 0),
                "in_progress": (q_in_progress or [{}])[0].get("cnt", 0),
                "completed_7d": (q_completed_7d or [{}])[0].get("cnt", 0),
                "agent_actions_24h": (q_actions_24h or [{}])[0].get("cnt", 0),
            },
            "workflows": q_workflows or [],
            "agent_actions_recent": q_actions or [],
        }
    except Exception as e:
        log.warning("Agent overview query failed (Lakebase tables may not exist): %s", e)
        return {"kpis": {}, "workflows": [], "agent_actions_recent": []}


@app.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: int):
    """Return a single workflow by ID (used by the workflow detail modal)."""
    rows = await asyncio.to_thread(
        run_pg_query,
        "SELECT * FROM workflows WHERE workflow_id = %s",
        (workflow_id,),
    )
    if not rows:
        raise HTTPException(404, f"Workflow {workflow_id} not found")
    return rows[0]


@app.patch("/api/workflows/{workflow_id}")
async def update_workflow(workflow_id: int, body: dict):
    """Update a workflow's status (approve/dismiss)."""
    new_status = body.get("status", "")
    if new_status not in ("approved", "dismissed"):
        raise HTTPException(400, "Status must be 'approved' or 'dismissed'")
    completed = "NOW()" if new_status in ("approved", "dismissed") else "NULL"
    result = await asyncio.to_thread(
        write_pg,
        f"UPDATE workflows SET status = %s, completed_at = {completed} WHERE workflow_id = %s RETURNING *",
        (new_status, workflow_id),
    )
    if not result:
        raise HTTPException(404, f"Workflow {workflow_id} not found")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# --- Add your domain routes below ---
# ═══════════════════════════════════════════════════════════════════════════
#
# Example:
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
    return FileResponse(
        os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "index.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )
