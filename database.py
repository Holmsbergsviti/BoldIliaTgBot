import asyncio
import os
import psycopg2
from contextlib import contextmanager

GOAL = 30_000  # RSD


def _get_conn():
    url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url)


@contextmanager
def _db():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── Sync implementations ──────────────────────────────────────────────────────

def _init_db_sync():
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pledges (
                    user_id    BIGINT PRIMARY KEY,
                    username   TEXT,
                    first_name TEXT,
                    amount     INTEGER NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)


def _upsert_pledge_sync(user_id: int, username: str, first_name: str, amount: int):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pledges (user_id, username, first_name, amount, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    username   = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    amount     = EXCLUDED.amount,
                    updated_at = NOW()
            """, (user_id, username, first_name, amount))


def _remove_pledge_sync(user_id: int):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pledges WHERE user_id = %s", (user_id,))


def _get_pledge_sync(user_id: int) -> int | None:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT amount FROM pledges WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return row[0] if row else None


def _get_total_sync() -> int:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(amount), 0) FROM pledges")
            return cur.fetchone()[0]


def _get_leaderboard_sync(limit: int = 10) -> list[tuple]:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT first_name, username, amount
                FROM pledges ORDER BY amount DESC LIMIT %s
            """, (limit,))
            return cur.fetchall()


def _get_donor_count_sync() -> int:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM pledges")
            return cur.fetchone()[0]


# ── Async wrappers ────────────────────────────────────────────────────────────

async def init_db():
    await asyncio.to_thread(_init_db_sync)


async def upsert_pledge(user_id, username, first_name, amount):
    await asyncio.to_thread(_upsert_pledge_sync, user_id, username, first_name, amount)


async def remove_pledge(user_id):
    await asyncio.to_thread(_remove_pledge_sync, user_id)


async def get_pledge(user_id) -> int | None:
    return await asyncio.to_thread(_get_pledge_sync, user_id)


async def get_total() -> int:
    return await asyncio.to_thread(_get_total_sync)


async def get_leaderboard(limit=10) -> list[tuple]:
    return await asyncio.to_thread(_get_leaderboard_sync, limit)


async def get_donor_count() -> int:
    return await asyncio.to_thread(_get_donor_count_sync)

