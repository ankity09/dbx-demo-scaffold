# Data Generation with dbldatagen and Databricks Serverless Jobs

This guide provides the complete, correct steps and configurations for generating data using dbldatagen and deploying to Databricks serverless jobs.

## Critical Success Factors

### Python and Serverless Environment Version Compatibility

**MOST IMPORTANT:** The serverless client version MUST match your local Python version.

| Serverless Client | Python Version | Databricks Connect |
|-------------------|----------------|-------------------|
| "1" | 3.10.12 | 14.3.7 |
| "2" | 3.11.9 | 15.4.5 |
| "3" | 3.12.3 | 16.4.2 |
| "4" | 3.12.3 | 17.0.1 |

**For Python 3.12 local development:**
- Use `client: "4"` in databricks.yml (serverless environment version 4)
- Use `databricks-connect==17.0.1` in dependencies
- Set `.python-version` to `3.12`
- Set `requires-python = ">=3.12"` in pyproject.toml

## Prerequisites

- Databricks workspace with access to serverless compute
- `uv` package manager installed
- `databricks` CLI installed and authenticated
- Access to Unity Catalog

## Project Structure

```
.
├── databricks.yml                      # Bundle configuration
├── pyproject.toml                      # Python project config
├── .python-version                     # Python version pinning (3.12)
├── generate_data.py                    # Python data generation script
├── notebooks/
│   └── generate_data_notebook.ipynb   # Notebook data generation
├── DEMO.md                            # Demo overview
├── TASKS.md                           # Task tracking
└── DATA_GENERATION.md                 # This file
```

## Step 1: Initialize Project with uv

```bash
# Initialize uv project
uv init --no-readme

# Set Python version to 3.12 (matches serverless environment version 4)
echo "3.12" > .python-version

# Add required dependencies with EXACT versions for client 4 compatibility
uv add "databricks-connect>=17.0.0,<=17.0.1" dbldatagen jmespath pyparsing
```

### Key Configuration Files

**pyproject.toml:**
```toml
[project]
name = "data-generation-demo"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "databricks-connect>=17.0.0,<=17.0.1",
    "dbldatagen>=0.4.0.post1",
    "jmespath>=1.0.1",
    "pyparsing>=3.2.5",
]
```

**.python-version:**
```
3.12
```

## Step 2: Create Python Data Generation Script

Create `generate_data.py` with the following key requirements:

### Critical Requirements for Serverless Compatibility

1. **Use DatabricksSession with environment dependencies for local execution:**
   ```python
   import os
   if os.environ.get('DATABRICKS_RUNTIME_VERSION'):
       # Running in Databricks
       spark = SparkSession.builder.getOrCreate()
   else:
       # Running locally with Databricks Connect
       from databricks.connect import DatabricksSession, DatabricksEnv

       # Create environment with UDF dependencies for local execution
       env = (DatabricksEnv()
              .withDependencies("dbldatagen==0.4.0.post1")
              .withDependencies("jmespath==1.0.1")
              .withDependencies("pyparsing==3.2.5"))

       spark = DatabricksSession.builder.serverless(True).withEnvironment(env).getOrCreate()
   ```

   **Why this is needed:** dbldatagen uses UDFs internally. UDFs execute on remote Databricks compute, so dependencies must be specified via `DatabricksEnv()` to be available during UDF execution. This feature requires Databricks Connect 16.4+.

2. **Avoid sparkContext (not supported in serverless):**
   ```python
   # DO NOT USE:
   # spark.sparkContext.appName

   # USE INSTEAD:
   print(f"Spark version: {spark.version}")
   ```

3. **Avoid dbldatagen parameters not supported:**
   ```python
   # DO NOT USE: unique=True parameter
   .withColumn("customer_id", "long", minValue=100000, maxValue=999999, unique=True)

   # USE INSTEAD:
   .withColumn("customer_id", "long", minValue=100000, maxValue=999999)
   ```

## Step 3: Create Databricks Bundle Configuration

Create `databricks.yml`:

### Critical Bundle Configuration Requirements

1. **Use client version "4" for Python 3.12:**
   ```yaml
   environments:
     - environment_key: serverless_env
       spec:
         client: "4"  # CRITICAL: Must be "4" for Python 3.12
         dependencies:
           - "dbldatagen==0.4.0.post1"
           - "jmespath==1.0.1"
           - "pyparsing==3.2.5"
   ```

2. **Use serverless environments, not clusters:**
   ```yaml
   tasks:
     - task_key: generate_data_python
       environment_key: serverless_env  # Use environment, not cluster
   ```

3. **DO NOT specify libraries at task level for serverless:**
   ```yaml
   # WRONG - Do not do this:
   tasks:
     - task_key: my_task
       libraries:
         - pypi:
             package: dbldatagen

   # CORRECT - Specify in environment:
   tasks:
     - task_key: my_task
       environment_key: serverless_env
   environments:
     - environment_key: serverless_env
       spec:
         client: "4"
         dependencies:
           - "dbldatagen==0.4.0.post1"
   ```

## Step 4: Local Testing with Databricks Connect

```bash
# Sync dependencies
uv sync

# Run locally using Databricks Connect
uv run python generate_data.py
```

## Step 5: Deploy and Run

```bash
# Validate bundle
databricks bundle validate

# Deploy bundle
databricks bundle deploy

# Run Python script job
databricks bundle run generate_data_python_job
```

## Common Issues and Solutions

### Issue 1: Python Version Mismatch
**Error:** `Python versions in the Spark Connect client and server are different`
**Solution:** Use Python 3.12 locally with `client: "4"` in databricks.yml.

### Issue 2: Libraries Not Found During Local Execution
**Error:** `ModuleNotFoundError: No module named 'dbldatagen'`
**Solution:** Use `DatabricksEnv().withDependencies()` when creating the Spark session locally.

### Issue 3: sparkContext Not Supported
**Error:** `[JVM_ATTRIBUTE_NOT_SUPPORTED] Attribute 'sparkContext' is not supported`
**Solution:** Remove all references to `spark.sparkContext`. Serverless doesn't support JVM attribute access.

### Issue 4: dbldatagen unique Parameter
**Error:** `DataGenError(msg='invalid column option unique')`
**Solution:** Remove `unique=True` parameter from column specifications.

## Version Compatibility Quick Reference

**Using Python 3.12 locally? (RECOMMENDED)**
```toml
requires-python = ">=3.12"
dependencies = ["databricks-connect>=17.0.0,<=17.0.1"]
```

```yaml
environments:
  - environment_key: serverless_env
    spec:
      client: "4"
```

## Data Generation Best Practices

1. **Test locally first** — Use Databricks Connect with `DatabricksEnv()` for rapid iteration
2. **Make code idempotent** — Use `.write.mode("overwrite")` to ensure reruns work
3. **Write to Unity Catalog** — Use `catalog.schema.table` naming
4. **Use partitioning** — Specify `partitions` in DataGenerator for performance
5. **Match dependencies** — Keep local `DatabricksEnv()` and job `environments.spec.dependencies` in sync
