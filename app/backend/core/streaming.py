"""
MAS (Multi-Agent Supervisor) SSE streaming proxy with action card detection
and automatic MCP tool approval.

SSE event protocol (frontend must handle all of these):
  - delta:            Text chunk from the final answer
  - tool_call:        Sub-agent invocation started
  - agent_switch:     MAS switched to a different sub-agent
  - sub_result:       Data returned from a sub-agent
  - action_card:      Entity created/referenced (e.g. PO, exception) — render as card
  - suggested_actions: Follow-up prompts based on tools used
  - error:            Error message
  - [DONE]:           Stream complete

MCP Auto-Approval:
  When MAS calls an External MCP Server tool, it emits an `mcp_approval_request`
  event and pauses. This module auto-approves those requests and re-invokes the
  MAS with the approval to continue execution. The caller sees seamless streaming.

Usage:
    from backend.core.streaming import stream_mas_chat
    return StreamingResponse(stream_mas_chat(message, history, action_card_tables), media_type="text/event-stream")
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
    """Get workspace host and auth header for MAS endpoint calls."""
    host = w.config.host.rstrip("/")
    auth_headers = w.config.authenticate()
    return host, auth_headers.get("Authorization", "")


# ── Action card table config ─────────────────────────────────────────────
# Override this list from your domain routes to detect custom entities.
# Each entry: {"table": "...", "card_type": "...", "id_col": "...", "title_template": "...", "actions": [...], "detail_cols": {...}}
#
# Example:
#   ACTION_CARD_TABLES = [
#       {"table": "purchase_orders", "card_type": "purchase_order", "id_col": "po_id",
#        "title_template": "Purchase Order {po_number}", "actions": ["approve", "dismiss"],
#        "detail_cols": {"from": "supplier_facility_id", "to": "destination_facility_id", "product": "product_id", "quantity": "quantity", "status": "status"}},
#   ]
ACTION_CARD_TABLES: list[dict] = []


async def _detect_chat_actions(final_text: str, lakebase_called: bool, tools_called: set) -> list[dict]:
    """Detect actionable entities created/referenced during chat and return action card events."""
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
                    # Fill {placeholder} in title from row data
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
    message: str,
    chat_history: list[dict],
    action_card_tables: list[dict] | None = None,
):
    """
    Async generator that yields SSE events from a MAS streaming invocation.

    Args:
        message: The user message to send.
        chat_history: List of {"role": "user"|"assistant", "content": "..."} dicts.
        action_card_tables: Optional override for ACTION_CARD_TABLES config.
    """
    if action_card_tables is not None:
        global ACTION_CARD_TABLES
        ACTION_CARD_TABLES = action_card_tables

    endpoint = f"mas-{MAS_TILE_ID}-endpoint" if MAS_TILE_ID else ""
    if not endpoint:
        yield f"data: {json.dumps({'type': 'error', 'text': 'MAS endpoint not configured. Set MAS_TILE_ID in app.yaml.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    final_text = ""
    lakebase_called = False
    tools_called = set()
    MAX_APPROVAL_ROUNDS = 10  # safety limit to prevent infinite loops

    try:
        host, auth = await asyncio.to_thread(_get_mas_auth)
        url = f"{host}/serving-endpoints/{endpoint}/invocations"
        input_messages = list(chat_history[-10:])
        approval_round = 0

        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            while approval_round <= MAX_APPROVAL_ROUNDS:
                payload = {"input": input_messages, "stream": True}
                round_output_items = []
                pending_approvals = []

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

                        if etype == "response.output_text.delta":
                            delta = evt.get("delta", "")
                            if delta:
                                final_text += delta
                                yield f"data: {json.dumps({'type': 'delta', 'text': delta, 'step': step})}\n\n"

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
                                log.info("MCP approval request: tool=%s server=%s id=%s", tool_name, server_label, item.get("id"))
                                pending_approvals.append(item)
                                tools_called.add(f"mcp:{server_label}:{tool_name}")
                                if "lakebase" in server_label.lower():
                                    lakebase_called = True
                                yield f"data: {json.dumps({'type': 'tool_call', 'agent': f'{server_label} → {tool_name}', 'step': step})}\n\n"

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

                # If no MCP approvals pending, we're done
                if not pending_approvals:
                    break

                # Auto-approve MCP tool calls and continue
                approval_round += 1
                log.info("Auto-approving %d MCP tool call(s) (round %d)", len(pending_approvals), approval_round)
                # IMPORTANT: Only include 'message' and 'mcp_approval_request' types.
                # function_call / function_call_output are internal MAS items and
                # cause errors if included as input.
                input_messages = list(chat_history[-10:])
                for item in round_output_items:
                    if item.get("type") in ("message", "mcp_approval_request"):
                        input_messages.append(item)
                for req in pending_approvals:
                    input_messages.append({
                        "type": "mcp_approval_response",
                        "id": f"approval-{approval_round}-{req.get('id', '')}",
                        "approval_request_id": req.get("id", ""),
                        "approve": True,
                    })

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
