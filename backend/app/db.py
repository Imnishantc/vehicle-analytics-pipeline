"""PostgreSQL access (psycopg3 pool). Credentials come from DATABASE_URL only."""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: Optional[ConnectionPool] = None
_lock = threading.Lock()


class DatabaseUnavailable(RuntimeError):
    pass


def get_pool() -> ConnectionPool:
    global _pool
    with _lock:
        if _pool is None:
            dsn = os.environ.get("DATABASE_URL")
            if not dsn:
                raise DatabaseUnavailable("DATABASE_URL is not configured")
            # open=False + lazy open means the API can start while PostgreSQL is down.
            _pool = ConnectionPool(dsn, min_size=1, max_size=int(os.environ.get("DB_POOL_MAX", "8")),
                                   kwargs={"row_factory": dict_row, "connect_timeout": 3},
                                   open=False, timeout=4)
            _pool.open(wait=False)
        return _pool


@contextmanager
def connection() -> Iterator:
    try:
        with get_pool().connection(timeout=4) as conn:
            yield conn
    except DatabaseUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - pool timeout / OperationalError
        import psycopg
        import psycopg_pool
        if isinstance(exc, (psycopg.OperationalError, psycopg_pool.PoolTimeout)):
            raise DatabaseUnavailable(str(exc)) from exc
        raise


def reset_pool() -> None:
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None
