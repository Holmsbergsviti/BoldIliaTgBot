import aiosqlite
import asyncio

DB_PATH = "boldilia.db"

GOAL = 30_000  # RSD


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pledges (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                amount     INTEGER NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def upsert_pledge(user_id: int, username: str, first_name: str, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO pledges (user_id, username, first_name, amount, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name,
                amount     = excluded.amount,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, username, first_name, amount))
        await db.commit()


async def remove_pledge(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pledges WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_pledge(user_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT amount FROM pledges WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def get_total() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COALESCE(SUM(amount), 0) FROM pledges") as cur:
            row = await cur.fetchone()
            return row[0]


async def get_leaderboard(limit: int = 10) -> list[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT first_name, username, amount
            FROM pledges
            ORDER BY amount DESC
            LIMIT ?
        """, (limit,)) as cur:
            return await cur.fetchall()


async def get_donor_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM pledges") as cur:
            row = await cur.fetchone()
            return row[0]
