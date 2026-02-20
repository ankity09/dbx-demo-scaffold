# Databricks notebook source
# Demo Scaffold — Data Generation
# Generates Delta Lake tables with domain-authentic data.
# Hash-based deterministic generation — re-running produces identical data.

# COMMAND ----------

# TODO: Replace with your catalog and schema
CATALOG = "TODO_CATALOG"
SCHEMA = "TODO_SCHEMA"
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

import hashlib
import math
from datetime import date, timedelta
from pyspark.sql import Row
from pyspark.sql.types import (
    StructType, StructField, IntegerType, StringType,
    DoubleType, DateType, LongType, BooleanType,
)

# Fixed reference date for deterministic output
TODAY = date(2026, 2, 15)


# ─── Deterministic hash-based generation functions ────────────────────────
# These produce repeatable "random" data from string seeds.

def _hash_float(seed: str, lo: float, hi: float) -> float:
    """Deterministic float in [lo, hi] from a seed string."""
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    return lo + (h / 0xFFFFFFFF) * (hi - lo)


def _hash_int(seed: str, lo: int, hi: int) -> int:
    return int(_hash_float(seed, lo, hi + 0.999))


def _hash_choice(seed: str, options: list):
    return options[_hash_int(seed, 0, len(options) - 1)]


def _hash_weighted(seed: str, options: list, weights: list):
    """Weighted random choice using hash."""
    h = _hash_float(seed, 0.0, 1.0)
    cumulative = 0.0
    total = sum(weights)
    for i, w in enumerate(weights):
        cumulative += w / total
        if h <= cumulative:
            return options[i]
    return options[-1]


def _hash_date(seed: str, start: date, end: date) -> date:
    """Deterministic date between start and end."""
    days_range = (end - start).days
    offset = _hash_int(seed, 0, max(0, days_range))
    return start + timedelta(days=offset)


# COMMAND ----------

# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS — Define your domain entities here
# ═══════════════════════════════════════════════════════════════════════════
#
# Pattern: Define lists of real/realistic entities for your customer's domain.
# Use actual facility names, product names, locations, etc. to make the demo authentic.
#
# Example for manufacturing:
#
# FACILITIES = [
#     {"id": "FAC-001", "name": "Chicago Assembly Plant", "type": "assembly", ...},
#     {"id": "FAC-002", "name": "Detroit Stamping Plant", "type": "stamping", ...},
# ]
#
# ASSETS = [
#     {"id": "AST-001", "name": "CNC Machine #1", "type": "cnc", "facility_id": "FAC-001", ...},
#     {"id": "AST-002", "name": "Hydraulic Press #3", "type": "press", "facility_id": "FAC-001", ...},
# ]

# TODO: Define your domain constants


# COMMAND ----------

# ═══════════════════════════════════════════════════════════════════════════
# TABLE GENERATION — Create and populate Delta Lake tables
# ═══════════════════════════════════════════════════════════════════════════
#
# Pattern for each table:
#   1. Define schema (StructType)
#   2. Generate rows using hash functions for determinism
#   3. Create DataFrame and write as Delta table
#
# Example:
#
# schema = StructType([
#     StructField("asset_id", StringType()),
#     StructField("asset_name", StringType()),
#     StructField("facility_id", StringType()),
#     StructField("install_date", DateType()),
#     StructField("health_score", DoubleType()),
# ])
#
# rows = []
# for asset in ASSETS:
#     rows.append(Row(
#         asset_id=asset["id"],
#         asset_name=asset["name"],
#         facility_id=asset["facility_id"],
#         install_date=_hash_date(f"install-{asset['id']}", date(2018, 1, 1), date(2024, 6, 1)),
#         health_score=round(_hash_float(f"health-{asset['id']}", 0.5, 1.0), 2),
#     ))
#
# df = spark.createDataFrame(rows, schema)
# df.write.mode("overwrite").saveAsTable("assets")
# print(f"Created assets table with {df.count()} rows")

# TODO: Generate your domain tables


# COMMAND ----------

# Verify all tables
# spark.sql("SHOW TABLES").display()
