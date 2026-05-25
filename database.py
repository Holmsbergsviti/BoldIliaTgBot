import asyncio
import os
import random
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS wheel_winner (
                    id       SERIAL PRIMARY KEY,
                    user_id  BIGINT,
                    name     TEXT,
                    username TEXT,
                    amount   INTEGER,
                    won_at   TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_ids (
                    chat_id  BIGINT PRIMARY KEY,
                    added_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)


def _upsert_pledge_sync(user_id, username, first_name, amount):
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


def _remove_pledge_sync(user_id):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pledges WHERE user_id = %s", (user_id,))


def _get_pledge_sync(user_id):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT amount FROM pledges WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return row[0] if row else None


def _get_total_sync():
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(amount), 0) FROM pledges")
            return cur.fetchone()[0]


def _get_leaderboard_sync(limit=10):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT first_name, username, amount
                FROM pledges ORDER BY amount DESC LIMIT %s
            """, (limit,))
            return cur.fetchall()


def _get_donor_count_sync():
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM pledges")
            return cur.fetchone()[0]


def _get_all_donors_sync():
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT user_id, first_name, username, amount
                FROM pledges ORDER BY amount DESC
            """)
            return cur.fetchall()


def _get_winner_sync():
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT user_id, name, username, amount, won_at
                FROM wheel_winner ORDER BY id DESC LIMIT 1
            """)
            return cur.fetchone()


def _set_winner_sync(user_id, name, username, amount):
    """Insert winner only if none exists yet. Returns True if this call inserted."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO wheel_winner (user_id, name, username, amount)
                SELECT %s, %s, %s, %s
                WHERE NOT EXISTS (SELECT 1 FROM wheel_winner)
                RETURNING id
            """, (user_id, name, username, amount))
            return cur.fetchone() is not None


def _select_winner_sync():
    rows = _get_all_donors_sync()
    if not rows:
        return None
    total = sum(r[3] for r in rows)
    pick = random.uniform(0, total)
    cumulative = 0
    for user_id, name, username, amount in rows:
        cumulative += amount
        if pick <= cumulative:
            return {"user_id": user_id, "name": name or username or "?",
                    "username": username, "amount": amount}
    r = rows[-1]
    return {"user_id": r[0], "name": r[1] or r[2] or "?",
            "username": r[2], "amount": r[3]}


def _save_chat_id_sync(chat_id):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chat_ids (chat_id) VALUES (%s)
                ON CONFLICT (chat_id) DO NOTHING
            """, (chat_id,))


def _get_chat_ids_sync():
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM chat_ids")
            return [r[0] for r in cur.fetchall()]


# ── Async wrappers ────────────────────────────────────────────────────────────

async def init_db():
    await asyncio.to_thread(_init_db_sync)

async def upsert_pledge(user_id, username, first_name, amount):
    await asyncio.to_thread(_upsert_pledge_sync, user_id, username, first_name, amount)

async def remove_pledge(user_id):
    await asyncio.to_thread(_remove_pledge_sync, user_id)

async def get_pledge(user_id):
    return await asyncio.to_thread(_get_pledge_sync, user_id)

async def get_total():
    return await asyncio.to_thread(_get_total_sync)

async def get_leaderboard(limit=10):
    return await asyncio.to_thread(_get_leaderboard_sync, limit)

async def get_donor_count():
    return await asyncio.to_thread(_get_donor_count_sync)

async def get_all_donors():
    return await asyncio.to_thread(_get_all_donors_sync)

async def get_winner():
    return await asyncio.to_thread(_get_winner_sync)

async def set_winner(user_id, name, username, amount):
    return await asyncio.to_thread(_set_winner_sync, user_id, name, username, amount)

async def select_winner():
    return await asyncio.to_thread(_select_winner_sync)

async def save_chat_id(chat_id):
    await asyncio.to_thread(_save_chat_id_sync, chat_id)

async def get_chat_ids():
    return await asyncio.to_thread(_get_chat_ids_sync)
