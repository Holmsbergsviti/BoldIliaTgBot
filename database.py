import os
import asyncpg

GOAL = 30_000  # RSD

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        database_url = os.environ["DATABASE_URL"]
        # asyncpg requires postgresql:// scheme
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        _pool = await asyncpg.create_pool(database_url)
    return _pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pledges (
                user_id    BIGINT PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                amount     INTEGER NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)


async def upsert_pledge(user_id: int, username: str, first_name: str, amount: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO pledges (user_id, username, first_name, amount, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                username   = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                amount     = EXCLUDED.amount,
                updated_at = NOW()
        """, user_id, username, first_name, amount)


async def remove_pledge(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM pledges WHERE user_id = $1", user_id)


async def get_pledge(user_id: int) -> int | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT amount FROM pledges WHERE user_id = $1", user_id)
        return row["amount"] if row else None


async def get_total() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM pledges")
        return int(val)


async def get_leaderboard(limit: int = 10) -> list[tuple]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT first_name, username, amount
            FROM pledges
            ORDER BY amount DESC
            LIMIT $1
        """, limit)
        return [(r["first_name"], r["username"], r["amount"]) for r in rows]


async def get_donor_count() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM pledges")
