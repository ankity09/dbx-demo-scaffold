# Databricks Demo Scaffold

Reusable scaffold for building customer demos on Databricks. Clone this repo, tell vibe what you want, and have a deployed demo in 2-4 hours.

**Architecture:** FastAPI backend + single-file HTML/JS frontend + Databricks Apps deployment.
**Stack:** Delta Lake (analytics) + Lakebase/PostgreSQL (OLTP) + Lakebase MCP Server (agent writes) + MAS Agent Bricks (AI chat) + Genie Space (NL queries).
**Compute:** All serverless — no classic clusters needed.

## CRITICAL: First-Time Setup

**When a user clones this scaffold and opens it in vibe, you MUST ask them for ALL of the following before generating any code:**

**Infrastructure (required first):**
1. **Demo Name** — What is this demo called? (e.g., "Apex Steel Predictive Maintenance")
2. **Customer** — Real or fictional customer name?
3. **Databricks Workspace URL** — e.g., `https://fe-sandbox-serverless-my-demo.cloud.databricks.com`
4. **Databricks CLI Profile** — e.g., `my-demo` (see FEVM Setup below)
5. **Catalog Name** — e.g., `serverless_my_demo_catalog` (FEVM auto-creates this)
6. **Schema Name** — e.g., `my_demo_schema` (you'll create this)
7. **SQL Warehouse ID** — From the workspace SQL Warehouses page
8. **Domain / Industry** — What industry is this demo for?
9. **Key Use Cases** — 2-4 use cases the demo should showcase

**UI Preferences (ask before building frontend):**
10. **Layout style** — Sidebar nav, top nav bar, or dashboard-first?
11. **Color scheme** — Dark industrial, clean medical, corporate blue, or custom brand colors?
12. **Dashboard content** — What should the main landing page show? (KPIs, charts, AI input, morning briefing, etc.)
13. **Additional pages** — What domain pages beyond AI Chat and Agent Workflows? (e.g., inventory, shipments, risk scores)

Fill in the Project Identity section below immediately after gathering this info. Then generate all code with these values — never leave TODOs in generated files.

## FEVM Workspace Setup

Most SAs use FE Vending Machine (FEVM) workspaces. These are serverless-only Databricks environments with auto-provisioned Unity Catalog.

### Creating a workspace
```bash
# Use vibe's built-in FEVM skill:
/databricks-fe-vm-workspace-deployment
# Choose: Serverless Deployment (Template 3, AWS, ~5-10 min)
# Name: use hyphens, e.g., my-customer-demo
# Lifetime: 30 days max
```

### Setting up the CLI profile
```bash
# After workspace is created, authenticate:
databricks auth login https://fe-sandbox-serverless-<name>.cloud.databricks.com --profile=<name>

# Verify:
databricks current-user me --profile=<name>
```

### FEVM naming conventions
- **Workspace URL:** `https://fe-sandbox-serverless-<name>.cloud.databricks.com`
- **Auto-created catalog:** `serverless_<name_with_underscores>_catalog` (hyphens become underscores)
- **Compute:** 100% serverless — SQL warehouses are pre-provisioned, no cluster management needed
- **Lifetime:** Up to 30 days, then must be recreated

## Project Identity

- **Demo Name:** TODO
- **Customer:** TODO
- **Workspace URL:** TODO
- **CLI Profile:** TODO
- **Catalog:** TODO
- **Schema:** TODO
- **SQL Warehouse ID:** TODO
- **Lakebase Instance:** TODO (use hyphens, NOT underscores)
- **Lakebase Database:** TODO
- **Lakebase MCP App Name:** TODO (e.g., `<demo-name>-lakebase-mcp`)
- **MAS Tile ID:** TODO (first 8 chars of tile_id)

## Architecture — 3 Layers

### Layer 1: CORE (never modify)
`app/backend/core/` — Battle-tested wiring extracted from production demos.
- `lakehouse.py` — `run_query()` for Delta Lake via Statement Execution API
- `lakebase.py` — PostgreSQL pool with OAuth token refresh and retry
- `streaming.py` — MAS SSE streaming proxy with action card detection
- `health.py` — 3-check health endpoint (SDK, SQL warehouse, Lakebase)
- `helpers.py` — `_safe()` input validation, `_extract_agent_response()` parser

`lakebase-mcp-server/` — Standalone Lakebase MCP server deployed as a separate Databricks App.
- `mcp_server.py` — 16 MCP tools (CRUD, DDL, SQL, transactions) + web UI
- `app.yaml` — Template pointing to Lakebase instance
- Deployed separately, wired to MAS as an `mcp_connection` sub-agent for writes

### Layer 2: SKELETON (fill placeholders)
- `app/app.yaml` — Deployment config with TODO placeholders
- `app/backend/main.py` — App assembly, imports core, mounts routes
- `lakebase/core_schema.sql` — 3 required tables (notes, agent_actions, workflows)
- `lakebase/domain_schema.sql` — Your domain-specific tables
- `notebooks/` — Schema setup, data generation, Lakebase seeding
- `agent_bricks/` — MAS and KA config templates
- `genie_spaces/` — Genie Space config template

### Layer 3: CUSTOMER (vibe generates)
- Domain-specific routes in `main.py`
- Frontend pages and visualizations
- Data model and generation scripts
- Agent prompts and tool descriptions
- Talk track and demo flow

### Lakebase MCP Server (agent writes)

The Lakebase MCP Server is a **separate Databricks App** that exposes Lakebase CRUD operations as MCP tools. MAS uses it as a sub-agent so the AI chat can write to Lakebase tables (create work orders, update statuses, etc.).

**How it works:**
1. Deploy `lakebase-mcp-server/` as a second Databricks App (e.g., `<demo>-lakebase-mcp`)
2. Create a UC HTTP connection pointing to `https://<mcp-app-url>/mcp/`
3. Add the MCP connection as a sub-agent in MAS config
4. MAS now has 16 tools for reading/writing any Lakebase table

**16 MCP Tools available to MAS:**
- READ: `list_tables`, `describe_table`, `read_query`, `list_schemas`, `get_connection_info`, `list_slow_queries`
- WRITE: `insert_record`, `update_records`, `delete_records`, `batch_insert`
- SQL: `execute_sql`, `execute_transaction`, `explain_query`
- DDL: `create_table`, `drop_table`, `alter_table`

See `lakebase-mcp-server/CLAUDE.md` for full deployment instructions.

## Core Module Reference

### `run_query(sql: str) -> list[dict]`
Execute SQL against Delta Lake via the Statement Execution API. Returns typed dicts (INT, DOUBLE, BOOLEAN auto-converted). Handles ResultManifest compatibility across SDK versions.

### `run_pg_query(sql: str, params=None) -> list[dict]`
Execute a read query against Lakebase. Auto-retries on stale token (InterfaceError/OperationalError). Returns dicts with Decimal→float and datetime→isoformat conversion.

### `write_pg(sql: str, params=None) -> Optional[dict]`
Execute INSERT/UPDATE/DELETE against Lakebase. Use `RETURNING *` to get the created/updated row back. Returns `{"affected": N}` for non-RETURNING queries.

### `_safe(val: str) -> str`
Whitelist regex validator for values injected into SQL strings. Raises HTTP 400 on injection attempts. Use for filter params in WHERE clauses.

### `_extract_agent_response(data: dict) -> str`
Parse MAS Agent Bricks response format. Handles `output[].content[].text`, plain string output, and legacy chat completions format.

### `stream_mas_chat(message, chat_history, action_card_tables) -> AsyncGenerator`
Async generator yielding SSE events from MAS. Configure `action_card_tables` to auto-detect entities created during chat.

### `health_router` (FastAPI APIRouter)
Include with `app.include_router(health_router)`. Exposes `GET /api/health` returning `{status: "healthy"|"degraded", checks: {sdk, sql_warehouse, lakebase}}`.

## Backend Patterns

### All blocking I/O must use asyncio.to_thread()
```python
# CORRECT
rows = await asyncio.to_thread(run_query, "SELECT * FROM my_table")
# WRONG — blocks the event loop
rows = run_query("SELECT * FROM my_table")
```

### Parallel queries with asyncio.gather()
```python
q_metrics, q_alerts, q_recent = await asyncio.gather(
    asyncio.to_thread(run_query, "SELECT COUNT(*) as total FROM items"),
    asyncio.to_thread(run_pg_query, "SELECT * FROM alerts WHERE status = 'open'"),
    asyncio.to_thread(run_pg_query, "SELECT * FROM activity ORDER BY created_at DESC LIMIT 10"),
)
```

### Use _safe() for all user-provided filter values
```python
@app.get("/api/items")
async def get_items(status: Optional[str] = None):
    where = []
    if status:
        where.append(f"status = '{_safe(status)}'")
    clause = "WHERE " + " AND ".join(where) if where else ""
    return await asyncio.to_thread(run_query, f"SELECT * FROM items {clause}")
```

### Use parameterized queries (%s) for Lakebase
```python
# CORRECT — parameterized
rows = run_pg_query("SELECT * FROM notes WHERE entity_id = %s", (entity_id,))
# WRONG — string interpolation
rows = run_pg_query(f"SELECT * FROM notes WHERE entity_id = '{entity_id}'")
```

### Pydantic models for request bodies
```python
from pydantic import BaseModel
class ItemCreate(BaseModel):
    name: str
    priority: str = "medium"
    description: str
    assigned_to: Optional[str] = None

@app.post("/api/items")
async def create_item(body: ItemCreate):
    return await asyncio.to_thread(
        write_pg,
        "INSERT INTO items (name, priority, description, assigned_to) VALUES (%s, %s, %s, %s) RETURNING *",
        (body.name, body.priority, body.description, body.assigned_to),
    )
```

## Frontend Patterns

### SSE Streaming Protocol
The chat UI handles these SSE event types (all implemented in `sendChat()`):
- `delta` — Text chunk from the final answer (stream into the answer div)
- `tool_call` — Sub-agent invoked (show as step indicator)
- `agent_switch` — MAS switched sub-agents (update step)
- `sub_result` — Data returned from sub-agent (show as completed step)
- `action_card` — Entity created/referenced (render interactive card)
- `suggested_actions` — Follow-up prompts (render as clickable buttons)
- `error` — Error message (display in red)
- `[DONE]` — Stream complete

### Action Cards
Configure `ACTION_CARD_TABLES` in `main.py` to auto-detect entities created during chat. Each card gets approve/dismiss buttons that PATCH the entity status via your API.

### CSS Variables for Theming
Override these in `:root` to rebrand. Variables use semantic names (`--primary`, `--accent`) not color names:
```css
:root {
  --primary: #1a2332;     /* Main dark — sidebar, headers */
  --accent: #f59e0b;      /* CTA / highlight color */
  --green: #10b981;       /* Success */
  --red: #ef4444;         /* Error/critical */
  --blue: #3b82f6;        /* Info */
}
```

### Adding New Pages
1. Add nav link in sidebar: `<a href="#" data-page="mypage">...</a>`
2. Add page div: `<div id="page-mypage" class="page">...</div>`
3. Add to PAGES array and PAGE_TITLES map in JS
4. Add `loadMypage()` function and call it from `navigate()`
5. Use `fetchApi()` to load data and render into the page div

### formatAgentName() Mapping
Customize this function to map MAS tool names to display labels:
```javascript
function formatAgentName(name) {
  const shortName = name.includes('__') ? name.split('__').pop() : name;
  const map = {
    'my_data_space': 'Data Query',
    'my_knowledge_base': 'Knowledge Base',
    'my_calculator': 'Calculator Tool',
    'mcp-lakebase-connection': 'Database (write)',
  };
  return map[shortName] || map[name] || shortName.replace(/[-_]/g, ' ');
}
```

## Frontend Generation Flow

**IMPORTANT: Before building any frontend pages, ask the user these questions:**

1. **Layout style** — Do you want a sidebar nav (default), top nav bar, or a dashboard-first layout?
2. **Color scheme** — What colors match the customer's brand? Options: dark industrial (navy/orange), clean medical (white/teal), corporate blue (navy/blue), or provide custom hex colors.
3. **Dashboard content** — What should the main dashboard show? KPI cards, charts, tables, a morning briefing, or a command-center style with AI input?
4. **Additional pages** — Beyond AI Chat and Agent Workflows (included), what domain pages are needed? (e.g., inventory, shipments, patients, risk scores)

**The template includes two starter pages that are already functional:**
- **AI Chat** — Full SSE streaming with sub-agent step indicators, action cards, follow-up suggestions. Do NOT rebuild this — customize the suggested prompts, welcome card text, and `formatAgentName()` mapping.
- **Agent Workflows** — Workflow cards with severity, status filters, centered modal with two-column layout (details + animated agent flow diagram), inline AI analysis. Do NOT rebuild this — customize `DOMAIN_AGENTS`, `WORKFLOW_AGENTS`, and `TYPE_LABELS`.

**The template layout (sidebar + topbar) is a minimal placeholder.** Replace it entirely based on the user's layout preference. The JS navigation system (`PAGES`, `PAGE_TITLES`, `navigate()`) supports any layout — just update the nav links and add page divs.

**When generating new pages:**
- Use the CSS component toolkit (`.kpi-row`, `.card`, `.grid-2`, `.badge-*`, `.btn-*`, `.filter-bar`, `table`, `.pill-*`) — these are layout-agnostic
- Use `fetchApi()` for all data loading, `showSkeleton()` for loading states, `animateKPIs()` for entrance animations
- Use `askAI(prompt)` to bridge any page to the chat (e.g., "Ask AI about this item")
- Follow the Adding New Pages pattern above

## Data Model Convention

| Layer | Technology | Purpose | Tables |
|-------|-----------|---------|--------|
| **Analytics** | Delta Lake | Historical data, aggregations, ML features | Domain-specific (e.g., assets, sensors, orders) |
| **OLTP** | Lakebase (PostgreSQL) | Real-time operations, agent writes | Core (notes, agent_actions, workflows) + domain-specific |
| **AI** | Genie Space | Natural language queries | Points at Delta Lake tables |
| **AI** | MAS Agent Bricks | Multi-agent orchestration | Orchestrates Genie, KA, UC functions, Lakebase |

## Deployment Sequence

**CRITICAL: Data notebooks (steps 1-6) MUST run BEFORE the app deployment (step 12). If you deploy the app first, users will see an empty dashboard with no data. The app queries Delta Lake tables that don't exist until the notebooks create them.**

### Phase A: Data + Infrastructure (do this FIRST)
1. **Create catalog/schema** — Run `notebooks/01_setup_schema.sql`
2. **Generate Delta Lake data** — Run `notebooks/02_generate_data.py` — **This creates the tables the app reads from**
3. **Verify tables** — `SHOW TABLES IN <catalog>.<schema>` should list your domain tables
4. **Create Lakebase instance** — Use Databricks UI or CLI. Instance name uses HYPHENS not underscores.
5. **Create database** — In the Lakebase instance
6. **Apply schemas** — `databricks psql <instance> --profile=<profile> -- -d <db> -f lakebase/core_schema.sql` then `domain_schema.sql`
7. **Seed Lakebase** — Run `notebooks/03_seed_lakebase.py` (uses `generate_database_credential()`, NOT `_header_factory`)

### Phase B: AI Layer
8. **Create Genie Space** — Use UI, then PATCH to add `table_identifiers`
9. **Grant Genie permissions** — `CAN_RUN` to app SP and users
10. **Deploy Lakebase MCP Server** — Deploy `lakebase-mcp-server/` as a separate app, create UC HTTP connection (see Lakebase MCP section)
11. **Create MAS** — POST to `/api/2.0/multi-agent-supervisors` with agent config (include Genie + MCP Lakebase connection)

### Phase C: App Deployment (do this LAST)
12. **Fill app.yaml** — Set warehouse ID, catalog, schema, MAS tile ID (first 8 chars), Lakebase instance/db
13. **Deploy app** — `databricks apps deploy <name> --source-code-path <path> --profile=<profile>`
14. **Register resources via API** — **CRITICAL: `app.yaml` resources are NOT automatically registered.** You MUST register them via the API, then redeploy:
```bash
databricks apps update <app-name> --json '{
  "resources": [
    {"name": "sql-warehouse", "sql_warehouse": {"id": "<warehouse-id>", "permission": "CAN_USE"}},
    {"name": "mas-endpoint", "serving_endpoint": {"name": "mas-<tile-8-chars>-endpoint", "permission": "CAN_QUERY"}},
    {"name": "database", "database": {"instance_name": "<instance>", "database_name": "<db>", "permission": "CAN_CONNECT_AND_CREATE"}}
  ]
}' --profile=<profile>
```
15. **Redeploy after resource registration** — `databricks apps deploy <name> --source-code-path <path> --profile=<profile>` — Databricks Apps only inject `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER` env vars at deploy time. If you skip this redeploy, Lakebase connections will fail.
16. **Grant permissions** — SQL warehouse CAN_USE, catalog/schema USE+SELECT to app SP
17. **Verify** — Visit the app URL in your browser (OAuth login required). Dashboard should show data. `GET /api/health` should return `{"status": "healthy"}` with all three checks passing (SDK, SQL warehouse, Lakebase). If any check fails, see the troubleshooting table below.

**Troubleshooting after deploy:**

| Symptom | Cause | Fix |
|---------|-------|-----|
| Health shows `lakebase: error` | Resources not registered via API, or not redeployed after registration | Run `databricks apps update` with all resources, then redeploy |
| Health shows `sql_warehouse: error` | Warehouse resource not registered or SP lacks CAN_USE | Register via API + grant CAN_USE to app SP |
| Dashboard shows zeros / empty | Delta Lake tables don't exist | Run `notebooks/02_generate_data.py` first |
| Dashboard loads but Lakebase pages empty | Lakebase schemas not applied or SP lacks table grants | Apply `core_schema.sql` + `domain_schema.sql`, grant SP access |
| 401 / empty `{}` from curl | Normal — Databricks Apps require browser OAuth | Open the app URL in a browser instead |

## Known Gotchas

### 1. Lakebase InterfaceError + OperationalError
The Lakebase OAuth token expires periodically. The core pool catches BOTH `psycopg2.InterfaceError` AND `psycopg2.OperationalError` and reinitializes with a fresh token. This is already handled in `core/lakebase.py` — do NOT modify.

### 2. Agent Brick endpoint naming
The MAS serving endpoint name is: `mas-{first_8_chars_of_tile_id}-endpoint`. Use the short 8-char prefix as `MAS_TILE_ID` in `app.yaml`, NOT the full UUID.

### 3. MAS PATCH requires full agents array
When updating MAS instructions via PATCH `/api/2.0/multi-agent-supervisors/{tile_id}`, you must include `name` AND the complete `agents` array, even if you're only changing instructions.

### 4. MCP create_or_update_mas doesn't support UC functions
The Databricks MCP tool for MAS doesn't support `unity_catalog_function` or `mcp_connection` agent types. Use the REST API directly for MAS configs that include these.

### 5. Lakebase instance uses hyphens
Instance names use hyphens (e.g., `my-demo-db`), NOT underscores. The Lakebase API will reject names with underscores.

### 6. Notebook auth: use generate_database_credential()
In serverless notebooks, `w.config._header_factory` tokens are NOT valid for Lakebase PG connections. Use:
```python
cred = w.database.generate_database_credential(instance_names=["my-instance"])
password = cred.token
```
`_header_factory` only works inside Databricks Apps where PGHOST/PGUSER are injected by the app resource system.

### 7. ResultManifest SDK compatibility
Newer SDK versions use `manifest.schema.columns` instead of `manifest.columns`. The core module handles this:
```python
columns = getattr(manifest, "columns", None) or getattr(manifest.schema, "columns", [])
```

### 8. app.yaml resources are NOT auto-registered — you MUST use the API
**This is the #1 cause of "app deployed but nothing works."** The `app.yaml` `resources:` section is declarative documentation only — it does NOT register resources with the Databricks Apps platform. You MUST register resources via `databricks apps update --json '{"resources": [...]}'` AND then redeploy. Without this:
- `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER` env vars are never injected → Lakebase connection fails
- The app SP has no access to the SQL warehouse → Delta Lake queries fail
- The app SP has no access to the MAS endpoint → chat returns 403

**The fix is always:** register resources via API → redeploy → verify with `/api/health`.

### 9. `databricks apps update` replaces all resources
PATCH/update to app resources replaces the entire resources array. Always include ALL resources in the update, not just the new one.

### 10. Genie Space table_identifiers
The UI doesn't always save table_identifiers correctly. Always PATCH the Genie Space via API to add tables:
```bash
databricks api patch /api/2.0/genie/spaces/{space_id} --json '{"table_identifiers": [{"catalog":"...", "schema":"...", "table":"..."}]}'
```

### 11. Grant CAN_RUN on Genie Space
The app SP needs CAN_RUN permission on the Genie Space. Also grant to the `account users` group for demo users.

### 12. UC function agents in MAS
UC function agents use this format in the MAS config:
```json
{"agent_type": "unity_catalog_function", "unity_catalog_function": {"uc_path": {"catalog": "...", "schema": "...", "name": "..."}}}
```

### 13. Empty app = data notebooks not run
If the app dashboard shows empty/zero metrics, the Delta Lake tables don't exist yet. You MUST run `02_generate_data.py` BEFORE deploying the app. The app queries tables that this notebook creates.

### 14. App health returns {} or 401
The Databricks Apps proxy requires OAuth authentication. `curl` from the terminal gets a 401 (`{}`). You must visit the app URL in a browser to trigger OAuth login and see the real app. The health endpoint works correctly when accessed through the browser.

### 15. Lakebase MCP trailing slash
The MCP endpoint is at `/mcp/` (with trailing slash). When creating the UC HTTP connection, set `base_path=/mcp/`. Without the trailing slash, Starlette redirects to `localhost:8000/mcp/` which breaks behind the Databricks App proxy.

### 16. MAS sends JSON strings for MCP tool params
MAS agents serialize nested objects as JSON strings instead of native objects. The Lakebase MCP server handles this via `_ensure_dict()` and `_ensure_list()` coercion, but if you build custom MCP tools, you must handle both formats.

### 17. CAN_USE on Lakebase MCP app for MAS
MAS External MCP Server goes through a Databricks MCP proxy that authenticates as a service principal. You must grant `CAN_USE` to the `users` group on the Lakebase MCP app, otherwise the proxy gets 401.

### 18. OAuth M2M for UC HTTP Connection
For the UC HTTP connection to the Lakebase MCP server, use Databricks OAuth M2M (not PAT). SP OAuth secrets must be created at the **Account Console** level (not workspace API). Connection fields: `host`, `port=443`, `base_path=/mcp/`, `client_id`, `client_secret`, `oauth_scope=all-apis`.

### 19. Agent Workflows page requires Lakebase tables
The Agent Workflows page fetches data from `/api/agent-overview`, which queries the Lakebase `workflows` and `agent_actions` tables (from `core_schema.sql`). If Lakebase is not set up, the page shows zeros or errors. **You MUST create the Lakebase instance, database, and apply `core_schema.sql` BEFORE deploying the app.** The frontend `loadAgentPage()` function calls the `/api/agent-overview` endpoint — if you leave it with placeholder/hardcoded values, the KPIs will be misleading.

### 20. Frontend has no dashboard — vibe must build it
The scaffold template only includes two starter pages (AI Chat + Agent Workflows). There is NO dashboard page by default. Vibe must generate the dashboard, layout, and domain pages based on the user's preferences. See the "Frontend Generation Flow" section for what to ask before building.

### 21. PGHOST not set after resource PATCH — must redeploy
If you add a `database` resource via `databricks api patch /api/2.0/apps/<name>` AFTER deploying, the app crashes with `psycopg2.OperationalError: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432"`. Databricks Apps only inject `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER` env vars **at deploy time**. A resource PATCH alone does NOT inject them. **Fix: Always redeploy after adding or changing resources.** The core `lakebase.py` guards against this — if `PGHOST` is empty, the pool is skipped and a clear warning is logged instead of crashing.

## Lakebase MCP Server Deployment

The scaffold includes a reusable Lakebase MCP server at `lakebase-mcp-server/`. This is deployed as a **separate Databricks App** and wired to MAS as a sub-agent.

### Deploy the MCP Server
```bash
# 1. Create the app
databricks apps create <demo>-lakebase-mcp --profile=<profile>

# 2. Update lakebase-mcp-server/app/app.yaml with your instance and database names

# 3. Sync and deploy
databricks sync ./lakebase-mcp-server/app /Workspace/Users/<you>/demos/<name>/lakebase-mcp/app --profile=<profile> --watch=false
databricks apps deploy <demo>-lakebase-mcp --source-code-path /Workspace/Users/<you>/demos/<name>/lakebase-mcp/app --profile=<profile>

# 4. Grant CAN_USE to users group (required for MAS proxy)
databricks api patch /api/2.0/permissions/apps/<demo>-lakebase-mcp \
  --json '{"access_control_list":[{"group_name":"users","permission_level":"CAN_USE"}]}' \
  --profile=<profile>

# 5. Grant table access to app SP
databricks psql <instance> --profile=<profile> -- -d <database> -c "
GRANT ALL ON ALL TABLES IN SCHEMA public TO \"<mcp-app-sp-client-id>\";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO \"<mcp-app-sp-client-id>\";
"
```

### Create UC HTTP Connection
Create a Unity Catalog connection so MAS can call the MCP server:
- **Type:** HTTP
- **URL:** `https://<mcp-app-url>/mcp/` (trailing slash required)
- **Auth:** Databricks OAuth M2M
- **Connection fields:** `host`, `port=443`, `base_path=/mcp/`, `client_id`, `client_secret`, `oauth_scope=all-apis`

### Wire to MAS
In `agent_bricks/mas_config.json`, add:
```json
{
  "agent_type": "mcp_connection",
  "mcp_connection": {
    "mcp_connection_id": "<connection-id-from-above>"
  },
  "name": "mcp-lakebase-connection",
  "description": "Write operational data to Lakebase PostgreSQL tables. Use for creating work orders, updating statuses, managing alerts, and other CRUD operations."
}
```

## What to Customize vs Keep

### DO NOT MODIFY
- `app/backend/core/` — All 5 core modules
- `app/requirements.txt` — Pinned dependencies
- `lakebase/core_schema.sql` — Required tables
- `lakebase-mcp-server/app/mcp_server.py` — MCP server code (works with any Lakebase database)

### CUSTOMIZE (fill placeholders)
- `app/app.yaml` — Replace all TODO values
- `app/backend/main.py` — Add domain routes after the marked section
- `lakebase/domain_schema.sql` — Add domain-specific tables
- `lakebase-mcp-server/app/app.yaml` — Set instance_name and database_name
- `notebooks/01_setup_schema.sql` — Set catalog/schema names
- `notebooks/02_generate_data.py` — Define domain constants, generate tables
- `notebooks/03_seed_lakebase.py` — Seed domain Lakebase tables
- `agent_bricks/mas_config.json` — Configure MAS agents (include Lakebase MCP connection)
- `genie_spaces/config.json` — Configure Genie Space tables
- `.mcp.json` — Set Databricks CLI profile

### BUILD FROM SCRATCH (vibe generates — ask user preferences first)
- **App layout and navigation** — sidebar, top nav, or dashboard-first (ask user)
- **Color scheme and branding** — update CSS variables in `:root` (ask user)
- **Dashboard page** — KPIs, charts, tables, briefing (ask user what metrics matter)
- **Domain-specific pages** — inventory, shipments, patients, etc. (ask user)
- Domain-specific API endpoints
- Agent prompts and tool descriptions
- Data model and constants for data generation
- Talk track and demo narrative

## Example Prompts for Vibe

### Example 1: Predictive Maintenance (dark industrial theme)
> Build me a predictive maintenance demo for Apex Steel. 5 factories, 200+ CNC machines, IoT sensors streaming vibration/temperature data. Use cases: anomaly detection, work order automation, spare parts optimization. I want a dark industrial theme (navy/orange), sidebar nav, and a dashboard with asset health KPIs and a morning briefing.

### Example 2: Healthcare Operations (clean medical theme)
> Build me a hospital operations demo for Baptist Health. Patient flow across 3 facilities — ER, OR scheduling, bed management. Key metrics: wait times, bed utilization, surgical throughput. I want a clean medical look (white/teal), top nav bar layout, and a dashboard showing real-time bed occupancy and patient queue.

### Example 3: Financial Risk (corporate theme)
> Build me a credit risk monitoring demo for First National Bank. Portfolio of 50K loans, real-time risk scoring, regulatory reporting. I want a corporate blue theme, dashboard-first layout with portfolio breakdown charts, and a risk score heatmap page. Use the scaffold's workflow management for alert handling.

## Reference

See `examples/supply_chain_routes.py` for a complete reference implementation showing all route patterns (KPI metrics, paginated lists, detail views, CRUD, workflows, filters).
