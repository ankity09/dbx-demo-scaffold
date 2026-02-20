"""
Health check endpoint that tests SDK, SQL warehouse, and Lakebase connectivity.

Usage:
    from backend.core.health import health_router
    app.include_router(health_router)
"""

import asyncio

from fastapi import APIRouter

from backend.core.lakehouse import run_query, w
from backend.core.lakebase import run_pg_query

health_router = APIRouter()


@health_router.get("/api/health")
async def health_check():
    """Returns {status: "healthy"|"degraded", checks: {sdk, sql_warehouse, lakebase}}."""
    checks = {}
    try:
        w.current_user.me()
        checks["sdk"] = "ok"
    except Exception as e:
        checks["sdk"] = str(e)
    try:
        await asyncio.to_thread(run_query, "SELECT 1")
        checks["sql_warehouse"] = "ok"
    except Exception as e:
        checks["sql_warehouse"] = str(e)
    try:
        await asyncio.to_thread(run_pg_query, "SELECT 1")
        checks["lakebase"] = "ok"
    except Exception as e:
        checks["lakebase"] = str(e)
    ok = all(v == "ok" for v in checks.values())
    return {"status": "healthy" if ok else "degraded", "checks": checks}
