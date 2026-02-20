# Quickstart: Clone to Deployed Demo in 2-4 Hours

## Prerequisites

- Claude Code / vibe installed
- `ai-dev-kit` cloned at `~/ai-dev-kit/` (for Databricks MCP server)
- Databricks CLI installed (`brew install databricks`)

## Phase 0: Workspace Setup (10 min)

**If you don't already have a workspace**, create one using FEVM:

```bash
# In vibe, run:
/databricks-fe-vm-workspace-deployment
# Choose: Serverless Deployment (Template 3, AWS)
# Name: use hyphens, e.g., my-customer-demo
# Lifetime: 30 days
```

**Set up CLI profile:**
```bash
databricks auth login https://fe-sandbox-serverless-<name>.cloud.databricks.com --profile=<name>

# Verify:
databricks current-user me --profile=<name>
```

**Note the auto-created catalog:** `serverless_<name_with_underscores>_catalog`

## Phase 1: Tell Vibe What You Want (15 min)

1. Clone or copy this scaffold to your demo directory:
   ```bash
   cp -r dbx-demo-scaffold/ my-customer-demo/
   cd my-customer-demo/
   ```

2. Update `.mcp.json` with your CLI profile name.

3. Open in Claude Code:
   ```bash
   claude
   ```

4. Give vibe a domain prompt. Be specific about the customer, industry, and key use cases:
   ```
   Build me a [DOMAIN] demo for [CUSTOMER]. They have [CONTEXT].
   Key use cases: [USE CASE 1], [USE CASE 2], [USE CASE 3].
   My workspace is [URL], profile is [PROFILE], catalog is [CATALOG].
   Use the scaffold core modules for all Lakebase/Lakehouse/MAS wiring.
   ```

5. Vibe will read `CLAUDE.md`, ask for any missing config, and generate:
   - Data model (constants for data generation)
   - Domain-specific Lakebase tables
   - API routes using core imports
   - Frontend pages
   - Agent prompts

## Phase 2: Create Data (MUST DO BEFORE APP DEPLOYMENT) (30 min)

**CRITICAL: If you skip this phase and deploy the app first, the dashboard will be completely empty. The app queries Delta Lake tables that only exist after running these notebooks.**

1. **Fill in catalog/schema** in `notebooks/01_setup_schema.sql` and `notebooks/02_generate_data.py`.

2. **Upload notebooks to your workspace:**
   ```bash
   databricks sync ./notebooks /Workspace/Users/<you>/demos/<name>/notebooks --profile=<profile>
   ```

3. **Run in order** (from Databricks workspace UI or via jobs API):
   - `01_setup_schema.sql` — Creates the catalog and schema
   - `02_generate_data.py` — Generates all Delta Lake tables

4. **Verify tables exist:**
   ```bash
   databricks api post /api/2.0/sql/statements/ --profile=<profile> --json '{
     "statement": "SHOW TABLES IN <catalog>.<schema>",
     "warehouse_id": "<warehouse_id>",
     "wait_timeout": "30s"
   }'
   ```
   You should see all your domain tables listed.

## Phase 3: Create Lakebase + Apply Schemas (20 min)

1. **Create Lakebase instance** (use hyphens, NOT underscores):
   ```bash
   # Via UI: Catalog > Databases > Create Instance
   # Or via CLI/API
   ```

2. **Create database** in the instance.

3. **Sync schema files:**
   ```bash
   databricks sync ./lakebase /Workspace/Users/<you>/demos/<name>/lakebase --profile=<profile> --watch=false
   ```

4. **Apply core schema** (notes, agent_actions, workflows):
   ```bash
   databricks psql <instance-name> --profile=<profile> -- -d <db-name> -f lakebase/core_schema.sql
   ```

5. **Apply domain schema:**
   ```bash
   databricks psql <instance-name> --profile=<profile> -- -d <db-name> -f lakebase/domain_schema.sql
   ```

6. **Seed Lakebase** — Run `notebooks/03_seed_lakebase.py`:
   - Update `PG_HOST` with your instance host
   - Update instance name in `generate_database_credential()` call
   - **IMPORTANT:** Use `generate_database_credential()`, NOT `_header_factory` for notebook auth

## Phase 4: Deploy Lakebase MCP Server (15 min)

The Lakebase MCP Server enables MAS to write to Lakebase tables. It's deployed as a separate app.

1. **Update `lakebase-mcp-server/app/app.yaml`** with your instance and database names.

2. **Create and deploy:**
   ```bash
   databricks apps create <demo>-lakebase-mcp --profile=<profile>
   databricks sync ./lakebase-mcp-server/app /Workspace/Users/<you>/demos/<name>/lakebase-mcp/app --profile=<profile> --watch=false
   databricks apps deploy <demo>-lakebase-mcp --source-code-path /Workspace/Users/<you>/demos/<name>/lakebase-mcp/app --profile=<profile>
   ```

3. **Grant permissions:**
   ```bash
   # CAN_USE for MAS proxy
   databricks api patch /api/2.0/permissions/apps/<demo>-lakebase-mcp \
     --json '{"access_control_list":[{"group_name":"users","permission_level":"CAN_USE"}]}' \
     --profile=<profile>

   # Table access for MCP app SP
   databricks psql <instance> --profile=<profile> -- -d <db> -c "
   GRANT ALL ON ALL TABLES IN SCHEMA public TO \"<mcp-app-sp-client-id>\";
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO \"<mcp-app-sp-client-id>\";
   "
   ```

4. **Create UC HTTP Connection** (for MAS to call the MCP server):
   - Type: HTTP, URL: `https://<mcp-app-url>/mcp/` (trailing slash!)
   - Auth: Databricks OAuth M2M
   - Note the connection ID for MAS config

5. **Verify:** Visit `https://<mcp-app-url>/` in browser — you should see the MCP server web UI.

## Phase 5: Create Genie Space + MAS (30 min)

### Genie Space

1. Create via Databricks UI: AI/BI > Genie > New Space
2. Add your Delta Lake tables as data sources
3. PATCH to ensure table_identifiers are saved:
   ```bash
   databricks api patch /api/2.0/genie/spaces/<space_id> --profile=<profile> --json '{
     "table_identifiers": [
       {"catalog": "<catalog>", "schema": "<schema>", "table": "<table1>"},
       {"catalog": "<catalog>", "schema": "<schema>", "table": "<table2>"}
     ]
   }'
   ```
4. Grant `CAN_RUN` to the app service principal and `account users` group

### Knowledge Assistant (optional)

1. Create via UI: Playground > New Knowledge Assistant
2. Upload domain documents (SOPs, manuals, etc.)
3. Note the KA ID from the URL

### MAS (Multi-Agent Supervisor)

1. Edit `agent_bricks/mas_config.json`:
   - Fill in Genie Space ID
   - Fill in KA ID (if using)
   - **Add MCP Lakebase connection ID** (from Phase 4)
   - Add UC function agents (if using)

2. Create MAS via REST API:
   ```bash
   databricks api post /api/2.0/multi-agent-supervisors --profile=<profile> --json @agent_bricks/mas_config.json
   ```

3. Note the **tile_id** from the response. The first 8 characters are your `MAS_TILE_ID`.

4. Update `app.yaml`:
   - Set `MAS_TILE_ID` to the first 8 chars of the tile_id
   - Set `mas-endpoint` resource name to `mas-<8chars>-endpoint`

## Phase 6: Deploy Demo App + Grant Permissions (15 min)

**Only do this after data notebooks have run (Phase 2) and Lakebase is set up (Phase 3).**

1. **Fill `app.yaml`** — Replace ALL TODO values:
   - `DATABRICKS_WAREHOUSE_ID`, `CATALOG`, `SCHEMA`, `MAS_TILE_ID`
   - Resource IDs for sql-warehouse, mas-endpoint, database

2. **Sync and deploy:**
   ```bash
   databricks sync ./app /Workspace/Users/<you>/demos/<name>/app --profile=<profile> --watch=false
   databricks apps deploy <app-name> --source-code-path /Workspace/Users/<you>/demos/<name>/app --profile=<profile>
   ```

3. **Add resources** (PATCH replaces all resources — include ALL):
   ```bash
   databricks api patch /api/2.0/apps/<app-name> --profile=<profile> --json '{
     "resources": [
       {"name": "sql-warehouse", "sql_warehouse": {"id": "<warehouse_id>", "permission": "CAN_USE"}},
       {"name": "mas-endpoint", "serving_endpoint": {"name": "mas-<tile_id>-endpoint", "permission": "CAN_QUERY"}},
       {"name": "database", "database": {"instance_name": "<instance>", "database_name": "<db>", "permission": "CAN_CONNECT_AND_CREATE"}}
     ]
   }'
   ```

4. **Grant SQL permissions to app service principal:**
   ```bash
   # Run each GRANT separately via the Statement Execution API
   databricks api post /api/2.0/sql/statements/ --profile=<profile> --json '{"statement": "GRANT USE CATALOG ON CATALOG <catalog> TO `<sp_client_id>`", "warehouse_id": "<wh_id>", "wait_timeout": "30s"}'
   databricks api post /api/2.0/sql/statements/ --profile=<profile> --json '{"statement": "GRANT USE SCHEMA ON SCHEMA <catalog>.<schema> TO `<sp_client_id>`", "warehouse_id": "<wh_id>", "wait_timeout": "30s"}'
   databricks api post /api/2.0/sql/statements/ --profile=<profile> --json '{"statement": "GRANT SELECT ON SCHEMA <catalog>.<schema> TO `<sp_client_id>`", "warehouse_id": "<wh_id>", "wait_timeout": "30s"}'
   ```
   **NOTE:** Statement Execution API only supports one statement at a time. Do NOT concatenate with semicolons.

5. **Verify:** Visit the app URL in your browser. The dashboard should show data.

## Phase 7: Customize Frontend + Practice Demo (1-2 hours)

1. **Add domain pages** — Tell vibe to add pages for your use cases:
   ```
   Add an [inventory/assets/patients] page with a data table,
   filter bar, and KPI cards. Fetch data from /api/my-domain/items.
   ```

2. **Customize branding** — Update CSS variables for customer colors:
   ```
   Change the accent color to match [customer] branding.
   Update the logo text and sidebar title.
   ```

3. **Add suggested prompts** — Customize the chat welcome prompts for your domain.

4. **Practice the demo flow** — Walk through the talk track:
   - Dashboard overview with KPIs
   - Drill into specific data views
   - AI chat with real questions
   - Show agent workflows with approve/dismiss
   - What-if scenarios

5. **Redeploy after changes:**
   ```bash
   databricks sync ./app /Workspace/Users/<you>/demos/<name>/app --profile=<profile> --watch=false
   databricks apps deploy <app-name> --source-code-path /Workspace/Users/<you>/demos/<name>/app --profile=<profile>
   ```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| **Dashboard shows empty/zero data** | Data notebooks not run | Run `02_generate_data.py` first, THEN redeploy |
| `/api/health` returns `{}` or 401 | Databricks Apps require OAuth | Access via browser, not curl |
| `/api/health` shows `sdk: error` | App SP not authenticated | Check app.yaml resources, redeploy |
| `/api/health` shows `sql_warehouse: error` | SP missing warehouse access | Grant CAN_USE on warehouse to SP |
| `/api/health` shows `lakebase: error` | DB resource not configured | PATCH app resources with database config |
| Chat returns "MAS endpoint not configured" | `MAS_TILE_ID` not set | Set to first 8 chars of MAS tile_id |
| Chat returns 403/404 | SP missing endpoint access | Grant CAN_QUERY on serving endpoint |
| Lakebase connection errors in notebook | Using wrong auth method | Use `generate_database_credential()`, not `_header_factory` |
| Genie Space returns no results | table_identifiers not set | PATCH Genie Space with table_identifiers |
| SQL GRANT fails with syntax error | Multiple statements in one call | Run each GRANT as a separate Statement API call |
| MAS can't write to Lakebase | MCP server not deployed | Deploy Lakebase MCP server (Phase 4) |
| MAS MCP proxy returns 401 | Missing permissions on MCP app | Grant CAN_USE to `users` group on MCP app |
