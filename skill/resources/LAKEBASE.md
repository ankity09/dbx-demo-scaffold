# Lakebase -- Operational Guide for Demos

Lakebase is Databricks' PostgreSQL-compatible OLTP database. It provides low-latency reads/writes for operational data alongside Lakehouse analytics. Any demo requiring real-time state (inventory, orders, chat history, sensor data, etc.) should use Lakebase.

## Key Concepts

- **Lakebase instances** are PostgreSQL-compatible databases managed by Databricks
- **Provisioned instances** are always-on; **autoscaling instances** support scale-to-zero
- Lakebase instances persist independently of the workspace -- they survive workspace recycling
- Unity Catalog (Lakehouse) tables do NOT survive workspace recycling on ephemeral FE-VM workspaces
- Connection uses standard PostgreSQL wire protocol (psycopg2, pg8000, etc.)
- Auth uses OAuth tokens from the Databricks SDK, not static passwords

## Deployment via CLI

```bash
# Create a provisioned instance
databricks database create-instance my-instance --profile <PROFILE>

# Wait for it to be available (takes 5-6 minutes from stopped state)
databricks database get-instance my-instance --profile <PROFILE>

# Connect via psql
databricks psql my-instance --profile <PROFILE> -- -d my_database

# Apply a schema file
databricks psql my-instance --profile <PROFILE> -- -d my_database -f schema.sql
```

## Using Lakebase with Databricks Apps

### app.yaml Database Resource

```yaml
resources:
  - name: database
    database:
      instance_name: my-instance
      database_name: my_database
      permission: CAN_CONNECT_AND_CREATE
```

When deployed, the platform auto-injects `PGHOST`, `PGPORT`, `PGDATABASE`, and `PGUSER` environment variables into the app container.

### CRITICAL: Resources Must Be Explicitly Registered

**The `app.yaml` resources block is NOT always picked up automatically on deploy.** After creating a new app, you MUST register resources via the update API:

```bash
databricks apps update <app-name> --json '{
  "resources": [
    {
      "name": "database",
      "database": {
        "instance_name": "my-instance",
        "database_name": "my_database",
        "permission": "CAN_CONNECT_AND_CREATE"
      }
    }
  ]
}' --profile <PROFILE>
```

Then redeploy so the app container picks up the new env vars.

### Service Principal Table Permissions

Tables created by your user (via `databricks psql`) are owned by you, not the app's service principal. The SP needs explicit grants:

```bash
# Get the app's SP client ID
databricks apps get <app-name> --profile <PROFILE>

# Grant permissions
databricks psql my-instance --profile <PROFILE> -- -d my_database -c "
GRANT ALL ON ALL TABLES IN SCHEMA public TO \"<sp-client-id>\";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO \"<sp-client-id>\";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO \"<sp-client-id>\";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO \"<sp-client-id>\";
"
```

## Ephemeral Workspace Lifecycle (FE-VM)

FE-VM workspaces are destroyed and recreated on a 14-day cycle.

| Asset | Survives Workspace Recycling? |
|-------|-------------------------------|
| Lakebase instance + data | YES |
| Unity Catalog tables | NO |
| Databricks App | NO (SP gets deleted) |
| Serving endpoints | NO |
| SQL Warehouses | NO |

### Recovery Procedure

```bash
# 1. Delete the broken app
databricks apps delete <app-name> --profile <PROFILE>

# 2. Recreate the app
databricks apps create <app-name> --profile <PROFILE>

# 3. Sync code to workspace
databricks workspace import-dir ./app /Workspace/Users/<email>/<app-folder> \
  --profile <PROFILE> --overwrite

# 4. Register resources (CRITICAL)
databricks apps update <app-name> --json '{
  "resources": [...]
}' --profile <PROFILE>

# 5. Deploy
databricks apps deploy <app-name> \
  --source-code-path /Workspace/Users/<email>/<app-folder> \
  --profile <PROFILE>

# 6. Grant Lakebase table permissions to new SP
databricks psql my-instance --profile <PROFILE> -- -d my_db -c "
GRANT ALL ON ALL TABLES IN SCHEMA public TO \"<new-sp-client-id>\";
..."
```

## Backend Connection Patterns

### psycopg2 Connection Pool with OAuth

```python
import psycopg2
import psycopg2.pool
from databricks.sdk import WorkspaceClient

_pg_pool = None
w = WorkspaceClient()

def _get_pg_token():
    header_factory = w.config._header_factory
    if callable(header_factory):
        result = header_factory()
        if isinstance(result, dict):
            return result.get("Authorization", "").removeprefix("Bearer ")
    return ""

def _init_pg_pool():
    global _pg_pool
    pg_host = os.environ.get("PGHOST")
    if not pg_host:
        return
    _pg_pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=1, maxconn=10,
        host=pg_host,
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "my_db"),
        user=os.environ.get("PGUSER", ""),
        password=_get_pg_token(),
        sslmode=os.environ.get("PGSSLMODE", "require"),
    )
```

## Lakebase Auth in Notebooks (Serverless)

In serverless notebooks, `w.config._header_factory` tokens are NOT valid for Lakebase PG connections. Use the credential generation API instead:

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
cred = w.database.generate_database_credential(instance_names=["my-instance"])
password = cred.token
```

## SQL Dialect Notes

Lakebase is PostgreSQL 16. Key differences from Spark SQL:

| Pattern | Lakebase (PostgreSQL) | Lakehouse (Spark SQL) |
|---------|----------------------|----------------------|
| Rounding | `ROUND(val::numeric, 4)` | `ROUND(val, 4)` |
| Random | `random()` | `rand()` |
| String concat | `'a' \|\| 'b'` | `CONCAT('a', 'b')` |
| Boolean | `TRUE` / `FALSE` | `true` / `false` |
| Auto-increment | `SERIAL` / `GENERATED ALWAYS` | Not supported |
| JSON | `JSONB` native type | `STRING` with schema_of_json |

## Autoscaling Lakebase

Autoscaling Lakebase supports scale-to-zero and branching:

```yaml
# app.yaml -- autoscaling mode (no database resource needed)
env:
  - name: LAKEBASE_PROJECT
    value: "my-project"
  - name: LAKEBASE_BRANCH
    value: "production"
  - name: LAKEBASE_DATABASE
    value: "my_db"
```
