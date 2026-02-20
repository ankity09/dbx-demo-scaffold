# Databricks notebook source
# Demo Scaffold — Seed Lakebase with operational data
# Run AFTER 02_generate_data.py and after creating the Lakebase instance/schema.

# COMMAND ----------

# MAGIC %pip install psycopg2-binary

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import psycopg2
import json
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# ═══════════════════════════════════════════════════════════════════════════
# IMPORTANT: Lakebase authentication in notebooks
# ═══════════════════════════════════════════════════════════════════════════
#
# CORRECT: Use the credential generation API
# This generates a short-lived token specifically for Lakebase PG connections.
#
cred = w.database.generate_database_credential(instance_names=["TODO-INSTANCE-NAME"])
token = cred.token
#
# DO NOT use w.config._header_factory in notebooks — those tokens are NOT
# valid for Lakebase PG connections. _header_factory only works inside
# Databricks Apps where PGHOST/PGUSER are injected by the app resource system.
#
# ═══════════════════════════════════════════════════════════════════════════

# COMMAND ----------

# Connection parameters — update these for your Lakebase instance
# Find these in the Lakebase instance details page.
PG_HOST = "TODO"          # e.g. "instance-abcd1234-5678-90ab-cdef-1234567890ab.database.cloud.databricks.com"
PG_PORT = 5432
PG_DATABASE = "TODO"      # e.g. "my_demo_db"
PG_USER = ""              # Leave empty for OAuth-based auth
PG_SSLMODE = "require"

conn = psycopg2.connect(
    host=PG_HOST,
    port=PG_PORT,
    dbname=PG_DATABASE,
    user=PG_USER,
    password=token,
    sslmode=PG_SSLMODE,
)
conn.autocommit = True
cur = conn.cursor()
print("Connected to Lakebase")

# COMMAND ----------

# Apply core schema (notes, agent_actions, workflows)
# TODO: Update the path to match your workspace location
schema_sql = open("/Workspace/Users/YOUR_EMAIL/demos/YOUR_DEMO/lakebase/core_schema.sql").read()
for stmt in schema_sql.split(";"):
    stmt = stmt.strip()
    if stmt and not stmt.startswith("--"):
        try:
            cur.execute(stmt)
        except Exception as e:
            print(f"  (skipped: {str(e)[:80]})")
print("Core schema applied")

# COMMAND ----------

# Apply domain schema
# TODO: Update the path to match your workspace location
domain_sql = open("/Workspace/Users/YOUR_EMAIL/demos/YOUR_DEMO/lakebase/domain_schema.sql").read()
for stmt in domain_sql.split(";"):
    stmt = stmt.strip()
    if stmt and not stmt.startswith("--"):
        try:
            cur.execute(stmt)
        except Exception as e:
            print(f"  (skipped: {str(e)[:80]})")
print("Domain schema applied")

# COMMAND ----------

# ═══════════════════════════════════════════════════════════════════════════
# SEED DATA — Add initial operational data to Lakebase tables
# ═══════════════════════════════════════════════════════════════════════════
#
# Pattern: Use parameterized queries (%s placeholders) for all inserts.
# Seed realistic data that makes the demo look "lived in."
#
# Example:
#
# import random
# random.seed(42)  # Deterministic seeding
#
# # Seed work orders
# statuses = ["draft", "submitted", "in_progress", "completed"]
# for i in range(50):
#     cur.execute(
#         """INSERT INTO work_orders (wo_number, asset_id, asset_name, priority, description, status)
#            VALUES (%s, %s, %s, %s, %s, %s)
#            ON CONFLICT (wo_number) DO NOTHING""",
#         (f"WO-{i+1:05d}", f"AST-{random.randint(1,20):03d}", f"Asset {i}",
#          random.choice(["low", "medium", "high", "critical"]),
#          f"Maintenance task {i+1}", random.choice(statuses)),
#     )
# print("Seeded work_orders")

# TODO: Seed your domain-specific tables

# COMMAND ----------

# Verify seeded data
# cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
# for row in cur.fetchall():
#     cur.execute(f"SELECT COUNT(*) FROM {row[0]}")
#     count = cur.fetchone()[0]
#     print(f"  {row[0]}: {count} rows")

# COMMAND ----------

cur.close()
conn.close()
print("Done — Lakebase seeded successfully")
