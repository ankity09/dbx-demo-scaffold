"""
Core modules — battle-tested wiring extracted from production demos.
DO NOT MODIFY these modules. Import and use them in your domain routes.
"""

from backend.core.lakehouse import run_query
from backend.core.lakebase import (
    run_pg_query,
    write_pg,
    _init_pg_pool,
)
from backend.core.streaming import stream_mas_chat, _get_mas_auth
from backend.core.health import health_check
from backend.core.helpers import _safe, _extract_agent_response

__all__ = [
    "run_query",
    "run_pg_query",
    "write_pg",
    "_init_pg_pool",
    "stream_mas_chat",
    "_get_mas_auth",
    "health_check",
    "_safe",
    "_extract_agent_response",
]
