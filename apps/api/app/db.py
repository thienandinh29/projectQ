from psycopg_pool import ConnectionPool


def create_pool(database_url: str) -> ConnectionPool:
    """Open a small pool; the demo is single-user so a few connections are plenty."""
    return ConnectionPool(database_url, min_size=1, max_size=5, open=True)


def ping(pool: ConnectionPool) -> bool:
    try:
        with pool.connection(timeout=2) as conn:
            conn.execute("select 1")
        return True
    except Exception:
        return False
