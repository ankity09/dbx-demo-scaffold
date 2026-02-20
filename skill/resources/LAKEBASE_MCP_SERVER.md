# Lakebase MCP Server -- Setup & MAS Integration

A reusable MCP (Model Context Protocol) server for Lakebase that gives AI agents full read/write/DDL access to your operational data. Deploy as a Databricks App, then connect it to a Multi-Agent Supervisor (MAS) as an External MCP Server agent.

## Architecture

```
AI Agent (MAS / Claude Code / etc.)
    |
    | MCP Protocol (StreamableHTTP)
    v
Lakebase MCP Server (Databricks App)
    |-- /          Web UI (database explorer, SQL editor, tool playground, docs)
    |-- /mcp/      MCP endpoint (stateless StreamableHTTP)
    |-- /api/*     REST API (21 endpoints)
    |-- /health    Health check
    |
    | psycopg2 (PostgreSQL wire protocol + auto token refresh)
    v
Lakebase Instance (Provisioned or Autoscaling)
```

## What It Provides

- **16 MCP tools** for schema inspection, CRUD, general SQL, DDL, transactions, query analysis, and performance monitoring
- **2 MCP resources** for table and schema discovery
- **3 MCP prompts** for database exploration, schema design, and query optimization
- **Web UI** with database explorer, SQL editor, tool playground, and documentation
- **REST API** (21 endpoints) for custom integrations
- **Database switcher** to switch between databases without redeploying
- Supports both **provisioned** and **autoscaling** Lakebase with automatic token refresh

## Deployment Steps

### Step 1: Create the App
```bash
databricks apps create lakebase-mcp-server --profile <PROFILE>
```

### Step 2: Configure app.yaml

**For provisioned Lakebase:**
```yaml
command:
  - python
  - mcp_server.py

resources:
  - name: database
    database:
      instance_name: my-instance
      database_name: my_database
      permission: CAN_CONNECT_AND_CREATE
```

### Step 3: Sync and Deploy
```bash
databricks workspace import-dir ./app /Workspace/Users/<email>/lakebase-mcp-server/app \
  --profile <PROFILE> --overwrite

databricks apps update lakebase-mcp-server --json '{
  "resources": [
    {"name": "database", "database": {"instance_name": "my-instance", "database_name": "my_database", "permission": "CAN_CONNECT_AND_CREATE"}}
  ]
}' --profile <PROFILE>

databricks apps deploy lakebase-mcp-server \
  --source-code-path /Workspace/Users/<email>/lakebase-mcp-server/app \
  --profile <PROFILE>
```

### Step 4: Grant Permissions
```bash
# Required for MAS MCP proxy to access the app
databricks api patch /api/2.0/permissions/apps/lakebase-mcp-server \
  --json '{"access_control_list":[{"group_name":"users","permission_level":"CAN_USE"}]}' \
  --profile <PROFILE>

# Grant table access to the app's service principal
databricks psql my-instance --profile <PROFILE> -- -d my_database -c "
GRANT ALL ON ALL TABLES IN SCHEMA public TO \"<app-sp-client-id>\";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO \"<app-sp-client-id>\";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO \"<app-sp-client-id>\";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO \"<app-sp-client-id>\";
"
```

## Connecting to MAS as a Subagent

### Step 1: Create a UC HTTP Connection

In the Databricks workspace UI:
1. Go to **Catalog > External Connections > Create Connection**
2. Connection type: **HTTP**
3. Configure:
   - **Host**: `<app-url>`
   - **Port**: `443`
   - **Base path**: `/mcp/` (trailing slash required)
   - **Auth type**: Databricks OAuth M2M
   - **Client ID**: Service principal application ID
   - **Client secret**: SP OAuth secret (create at **Account Console > App Connections**)
   - **OAuth scope**: `all-apis`

### Step 2: Add External MCP Server Agent to MAS

In your MAS Supervisor configuration:
1. Click **Add Agent > External MCP Server**
2. Select the UC HTTP connection from Step 1
3. Set the agent description (be specific about what data lives in your Lakebase)

### Step 3: Test in MAS Playground

Try these queries:
- "What tables are in the database?"
- "Show me the top 10 rows from the orders table"
- "Insert a new record into the notes table"

## MAS API Note

The MCP `create_or_update_mas` tool does **NOT** support the External MCP Server agent type. You must add MCP agents via the MAS UI or the REST API directly:

```bash
databricks api patch "/api/2.0/multi-agent-supervisors/<tile-id>" --json '{
  "name": "my-supervisor",
  "agents": [
    {
      "agent_type": "mcp_connection",
      "mcp_connection": {
        "mcp_connection_id": "<connection-id>"
      },
      "name": "mcp-lakebase-connection",
      "description": "Execute Lakebase database operations..."
    }
  ]
}' --profile <PROFILE>
```

**IMPORTANT:** PATCH requires the `name` field plus the full `agents` array, even if you're only updating one agent.

## MCP Tools Reference (16)

| Category | Tool | Description |
|----------|------|-------------|
| Schema | `list_tables` | List all tables with row counts |
| Schema | `describe_table` | Column details, types, PKs |
| Schema | `list_schemas` | List all schemas |
| Schema | `get_connection_info` | Connection details (no password) |
| Data | `read_query` | Execute SELECT queries |
| Data | `insert_record` | Insert single record (JSONB-aware) |
| Data | `update_records` | Update rows matching WHERE |
| Data | `delete_records` | Delete rows matching WHERE |
| Data | `batch_insert` | Insert multiple records |
| SQL | `execute_sql` | Execute any SQL (auto-detects type) |
| SQL | `execute_transaction` | Atomic multi-statement transaction |
| SQL | `explain_query` | EXPLAIN ANALYZE with JSON output |
| DDL | `create_table` | CREATE TABLE with IF NOT EXISTS |
| DDL | `drop_table` | DROP TABLE with confirm safety gate |
| DDL | `alter_table` | Add/drop/rename/alter columns |
| Perf | `list_slow_queries` | Top N slow queries |

## Known Gotchas

1. **Trailing slash on MCP endpoint:** Use `/mcp/` not `/mcp` in the UC HTTP connection base path.
2. **MAS sends JSON strings:** MAS serializes nested objects as JSON strings. Handle both formats.
3. **CAN_USE for users group:** MAS MCP proxy needs `CAN_USE` on the app.
4. **OAuth M2M for UC HTTP Connection:** SP OAuth secrets must be created at the **Account Console** level.
5. **Table permissions after app recreation:** New SP needs fresh grants to existing tables.

## Source Code

The reference implementation is at: https://github.com/ankity09/lakebase-mcp-server
