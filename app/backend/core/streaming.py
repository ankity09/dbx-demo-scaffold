"""
MAS (Multi-Agent Supervisor) SSE streaming proxy with MCP approval flow.

Supports two MCP approval modes (controlled by `mcp_auto_approve` parameter):
  - Auto-approve (default): Backend auto-approves all MCP tool calls. Simpler,
    but the user doesn't see individual tool approvals.
  - User approval: Backend pauses on MCP approval requests, sends them to the
    frontend as `mcp_approval` SSE events. The frontend shows an approval UI
    and sends the decision back. Requires the user's OBO token.

SSE event protocol (frontend must handle all of these):
  - delta:            Text chunk from the final answer
  - tool_call:        Sub-agent invocation started
  - agent_switch:     MAS switched to a different sub-agent
  - sub_result:       Data returned from a sub-agent
  - mcp_approval:     MCP tool needs user approval (user-approval mode only)
  - action_card:      Entity created/referenced (e.g. PO, exception) — render as card
  - suggested_actions: Follow-up prompts based on tools used
  - error:            Error message
  - [DONE]:           Stream complete

OBO (On-Behalf-Of-User) Setup:
  The app must use the user's OAuth token for MAS calls when MCP tools are
  involved. The Databricks App proxy forwards it as `x-forwarded-access-token`.
  Required app config:
    databricks api patch /api/2.0/apps/<name> --json '{"user_api_scopes": ["serving.serving-endpoints", "sql"]}'

Usage:
    from backend.core.streaming import stream_mas_chat, mcp_pending_state
    # New message:
    return StreamingResponse(stream_mas_chat(msg, history, user_token=token), ...)
    # MCP approval continuation:
    return StreamingResponse(stream_mas_chat(None, history, user_token=token, approve_mcp=True), ...)
"""

import asyncio
import json
import logging
import os

import httpx
from databricks.sdk import WorkspaceClient

from backend.core.lakebase import run_pg_query

log = logging.getLogger("streaming")

w = WorkspaceClient()

MAS_TILE_ID = os.getenv("MAS_TILE_ID", "")


def _get_mas_auth() -> tuple[str, str]:
    """Get workspace host and SP auth header (fallback when no user token)."""
    host = w.config.host.rstrip("/")
    auth_headers = w.config.authenticate()
    return host, auth_headers.get("Authorization", "")


# ── MCP Approval State ──────────────────────────────────────────────────────
# When MAS requests MCP tool approval in user-approval mode, we pause the
# stream and save state here. When the user approves, the next call to
# stream_mas_chat (with approve_mcp=True) resumes with full context.
mcp_pending_state: dict | None = None


# ── Action card table config ─────────────────────────────────────────────
# Override from domain routes. Each entry:
#   {"table": "...", "card_type": "...", "id_col": "...",
#    "title_template": "...", "actions": [...], "detail_cols": {...}}
ACTION_CARD_TABLES: list[dict] = []


async def _detect_chat_actions(final_text: str, lakebase_called: bool, tools_called: set) -> list[dict]:
    """Detect actionable entities created/referenced during chat."""
    cards = []

    if lakebase_called and ACTION_CARD_TABLES:
        for tbl_config in ACTION_CARD_TABLES:
            try:
                recent = await asyncio.to_thread(
                    run_pg_query,
                    f"SELECT * FROM {tbl_config['table']} WHERE created_at >= NOW() - INTERVAL '3 minutes' ORDER BY created_at DESC LIMIT 3",
                )
                for row in recent:
                    details = {}
                    for display_key, db_col in tbl_config.get("detail_cols", {}).items():
                        val = row.get(db_col, "")
                        details[display_key] = str(val) if val is not None else ""

                    title = tbl_config.get("title_template", tbl_config["card_type"])
                    try:
                        title = title.format(**row)
                    except (KeyError, IndexError):
                        pass

                    cards.append({
                        "type": "action_card",
                        "card_type": tbl_config["card_type"],
                        "entity_id": row.get(tbl_config["id_col"]),
                        "title": title,
                        "details": details,
                        "actions": tbl_config.get("actions", ["approve", "dismiss"]),
                    })
            except Exception as e:
                log.warning("Action card query error for %s: %s", tbl_config["table"], e)

    # Suggested follow-up actions based on tools used
    followups = []
    tool_names_lower = {t.lower() for t in tools_called}
    if any("weather" in t for t in tool_names_lower):
        followups.append({"label": "Check affected items", "prompt": "Which items are affected by the conditions you just found?"})
    if any("reorder" in t or "calculator" in t for t in tool_names_lower):
        followups.append({"label": "Create order", "prompt": "Create an order based on the calculation you just did"})
    if any("forecast" in t or "demand" in t for t in tool_names_lower):
        followups.append({"label": "Plan transfers", "prompt": "Based on the forecast, what transfers should we plan?"})
    if followups:
        cards.append({"type": "suggested_actions", "actions": followups[:3]})

    return cards


async def stream_mas_chat(
    message: str | None,
    chat_history: list[dict],
    action_card_tables: list[dict] | None = None,
    user_token: str = "",
    mcp_auto_approve: bool = True,
    approve_mcp: bool | None = None,
):
    """
    Async generator that yields SSE events from a MAS streaming invocation.

    Args:
        message: User message (None when continuing from MCP approval).
        chat_history: List of {"role": "user"|"assistant", "content": "..."} dicts.
        action_card_tables: Optional override for ACTION_CARD_TABLES config.
        user_token: User's OAuth token from x-forwarded-access-token header.
                    Required for MCP tools to work (MAS needs user identity).
        mcp_auto_approve: If True, auto-approve MCP tools in backend.
                          If False, pause and send approval request to frontend.
        approve_mcp: True/False when continuing from a user MCP approval decision.
    """
    global mcp_pending_state

    if action_card_tables is not None:
        global ACTION_CARD_TABLES
        ACTION_CARD_TABLES = action_card_tables

    endpoint = f"mas-{MAS_TILE_ID}-endpoint" if MAS_TILE_ID else ""
    if not endpoint:
        yield f"data: {json.dumps({'type': 'error', 'text': 'MAS endpoint not configured. Set MAS_TILE_ID in app.yaml.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # ── Determine starting state ────────────────────────────────────────
    if approve_mcp is not None and mcp_pending_state:
        # Continuing from user MCP approval
        log.info("MCP approval received: approve=%s", approve_mcp)
        all_accumulated = mcp_pending_state["accumulated"]
        tools_called = mcp_pending_state["tools_called"]
        lakebase_called = mcp_pending_state["lakebase_called"]
        approval_round = mcp_pending_state["round"]

        for req in mcp_pending_state["pending"]:
            all_accumulated.append({
                "type": "mcp_approval_response",
                "id": f"approval-{approval_round}-{req.get('id', '')}",
                "approval_request_id": req.get("id", ""),
                "approve": bool(approve_mcp),
            })
        start_messages = list(chat_history[-10:]) + all_accumulated
        mcp_pending_state = None
    elif approve_mcp is not None and not mcp_pending_state:
        yield f"data: {json.dumps({'type': 'error', 'text': 'No pending MCP approval.'})}\n\n"
        yield "data: [DONE]\n\n"
        return
    else:
        # New user message
        start_messages = list(chat_history[-10:])
        all_accumulated: list[dict] = []
        tools_called: set = set()
        lakebase_called = False
        approval_round = 0

    final_text = ""
    MAX_ROUNDS = 10

    try:
        host = w.config.host.rstrip("/")
        # Use user token for MAS calls (required for MCP tools)
        if user_token:
            auth = f"Bearer {user_token}"
        else:
            _, auth = await asyncio.to_thread(_get_mas_auth)
            log.warning("No user token — using SP auth. MCP tools may not work.")
        url = f"{host}/serving-endpoints/{endpoint}/invocations"
        input_messages = start_messages

        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            while approval_round <= MAX_ROUNDS:
                payload = {"input": input_messages, "stream": True, "max_turns": 15}
                round_output_items: list[dict] = []
                pending_approvals: list[dict] = []

                async with client.stream(
                    "POST", url,
                    json=payload,
                    headers={"Authorization": auth, "Content-Type": "application/json"},
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:]
                        if raw == "[DONE]":
                            break
                        try:
                            evt = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        etype = evt.get("type", "")
                        step = evt.get("step", 0)

                        # Text delta
                        if etype == "response.output_text.delta":
                            delta = evt.get("delta", "")
                            if delta:
                                final_text += delta
                                yield f"data: {json.dumps({'type': 'delta', 'text': delta, 'step': step})}\n\n"

                        # Completed output item
                        elif etype == "response.output_item.done":
                            item = evt.get("item", {})
                            item_type = item.get("type", "")
                            round_output_items.append(item)

                            if item_type == "function_call":
                                agent_name = item.get("name", "")
                                tools_called.add(agent_name)
                                if "lakebase" in agent_name.lower():
                                    lakebase_called = True
                                yield f"data: {json.dumps({'type': 'tool_call', 'agent': agent_name, 'step': step})}\n\n"

                            elif item_type == "mcp_approval_request":
                                tool_name = item.get("name", "unknown")
                                server_label = item.get("server_label", "")
                                pending_approvals.append(item)
                                tools_called.add(f"mcp:{server_label}:{tool_name}")
                                if "lakebase" in server_label.lower():
                                    lakebase_called = True
                                yield f"data: {json.dumps({'type': 'tool_call', 'agent': f'Lakebase → {tool_name}', 'step': step})}\n\n"

                            elif item_type == "function_call_output":
                                output_text = item.get("output", "")
                                if output_text and len(output_text) > 5:
                                    yield f"data: {json.dumps({'type': 'sub_result', 'text': output_text[:2000], 'step': step})}\n\n"

                            elif item_type == "message":
                                content = item.get("content", [])
                                for block in content:
                                    text_val = block.get("text", "")
                                    if text_val.startswith("<name>") and text_val.endswith("</name>"):
                                        agent_name = text_val[6:-7]
                                        yield f"data: {json.dumps({'type': 'agent_switch', 'agent': agent_name, 'step': step})}\n\n"
                                    elif text_val and len(text_val) > 5 and not text_val.startswith("<"):
                                        yield f"data: {json.dumps({'type': 'sub_result', 'text': text_val, 'step': step})}\n\n"
                                if item.get("role") == "assistant" and step > 1:
                                    for block in content:
                                        if block.get("type") == "output_text" and block.get("text"):
                                            final_text = block["text"]

                # No pending approvals → done
                if not pending_approvals:
                    break

                # ── MCP approval handling ────────────────────────────────────
                approval_round += 1
                all_accumulated.extend(round_output_items)

                if mcp_auto_approve:
                    # Auto-approve: add approval responses and continue immediately
                    log.info("MCP auto-approve round %d: %s", approval_round, [p.get("name") for p in pending_approvals])
                    for req in pending_approvals:
                        all_accumulated.append({
                            "type": "mcp_approval_response",
                            "id": f"approval-{approval_round}-{req.get('id', '')}",
                            "approval_request_id": req.get("id", ""),
                            "approve": True,
                        })
                    input_messages = list(chat_history[-10:]) + all_accumulated
                else:
                    # User approval: pause, save state, send to frontend
                    mcp_pending_state = {
                        "accumulated": all_accumulated,
                        "pending": pending_approvals,
                        "tools_called": tools_called,
                        "lakebase_called": lakebase_called,
                        "round": approval_round,
                    }
                    approval_tools = []
                    for p in pending_approvals:
                        args_raw = p.get("arguments", "{}")
                        try:
                            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                        except (json.JSONDecodeError, TypeError):
                            args = {}
                        approval_tools.append({
                            "name": p.get("name", "unknown"),
                            "server": p.get("server_label", ""),
                            "arguments": args,
                        })
                    yield f"data: {json.dumps({'type': 'mcp_approval', 'tools': approval_tools})}\n\n"
                    log.info("MCP approval pause: round=%d tools=%s", approval_round, [t["name"] for t in approval_tools])
                    yield "data: [DONE]\n\n"
                    return  # Exit — frontend will send approval and start new stream

    except Exception as e:
        log.error("MAS stream error: %s", e)
        yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

    # Emit action cards
    try:
        action_cards = await _detect_chat_actions(final_text, lakebase_called, tools_called)
        for card in action_cards:
            yield f"data: {json.dumps(card)}\n\n"
    except Exception as e:
        log.warning("Action card detection error: %s", e)

    yield "data: [DONE]\n\n"
