"""CleanLondon Database Connection Management — connection pooling, transactions and helpers."""

import queue
import re
import threading
from contextlib import contextmanager
from typing import Optional

import pymysql
import pymysql.cursors
from fastapi import HTTPException, Request, status

from app.core.config import (
    DB_HOST,
    DB_PORT,
    DB_USER,
    DB_PASSWORD,
    DB_NAME,
    DB_POOL_SIZE,
    DB_POOL_TIMEOUT_SECONDS,
)

# ---------------------------------------------------------------------------
# Connection Pool
# ---------------------------------------------------------------------------
_DB_POOL = queue.LifoQueue(maxsize=DB_POOL_SIZE)
_DB_POOL_LOCK = threading.Lock()
_DB_POOL_CREATED = 0


def _create_db_connection():
    """Create a new MySQL connection."""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def get_db_connection():
    """Get a connection from the pool, creating a new one if needed."""
    global _DB_POOL_CREATED
    try:
        conn = _DB_POOL.get_nowait()
        conn.ping(reconnect=True)
        return conn
    except queue.Empty:
        with _DB_POOL_LOCK:
            if _DB_POOL_CREATED < DB_POOL_SIZE:
                _DB_POOL_CREATED += 1
                try:
                    return _create_db_connection()
                except Exception as e:
                    _DB_POOL_CREATED -= 1
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"Database connection error: {str(e)}. Ensure MySQL is running on {DB_HOST}:{DB_PORT}.",
                    )
        try:
            conn = _DB_POOL.get(timeout=DB_POOL_TIMEOUT_SECONDS)
            conn.ping(reconnect=True)
            return conn
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database connection pool is exhausted or unavailable: {str(e)}",
            )
    except Exception:
        # Drop a stale pooled connection and create a replacement.
        with _DB_POOL_LOCK:
            _DB_POOL_CREATED = max(0, _DB_POOL_CREATED - 1)
        try:
            conn.close()
        except Exception:
            pass
        try:
            with _DB_POOL_LOCK:
                _DB_POOL_CREATED += 1
            return _create_db_connection()
        except Exception as e:
            with _DB_POOL_LOCK:
                _DB_POOL_CREATED = max(0, _DB_POOL_CREATED - 1)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database connection error: {str(e)}. Ensure MySQL is running on {DB_HOST}:{DB_PORT}.",
            )


def release_db_connection(conn):
    """Return a connection to the pool."""
    try:
        conn.ping(reconnect=True)
        _DB_POOL.put(conn, timeout=DB_POOL_TIMEOUT_SECONDS)
    except Exception:
        global _DB_POOL_CREATED
        try:
            conn.close()
        except Exception:
            pass
        finally:
            with _DB_POOL_LOCK:
                _DB_POOL_CREATED = max(0, _DB_POOL_CREATED - 1)


@contextmanager
def get_db():
    """Context manager that yields a database connection and returns it to the pool."""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        release_db_connection(conn)


def get_idempotency_key(request: Request, payload_key: Optional[str] = None) -> Optional[str]:
    """Prefer the standard header while retaining compatibility with older clients."""
    header_key = request.headers.get("Idempotency-Key")
    if header_key and payload_key and header_key != payload_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header does not match the request payload.",
        )
    key = header_key or payload_key
    if key and (len(key) > 100 or not re.fullmatch(r"[A-Za-z0-9._:-]+", key)):
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key.")
    return key


@contextmanager
def get_transaction():
    """Provide an explicit transaction for operations that require row locking."""
    conn = get_db_connection()
    try:
        conn.begin()
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db_connection(conn)
