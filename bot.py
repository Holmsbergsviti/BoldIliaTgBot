import asyncio
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from aiohttp import web
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    MenuButtonWebApp,
)
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

import database as db

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", 8080))

GOAL = 30_000
DEADLINE = datetime(2026, 8, 29, tzinfo=timezone.utc)
STATIC_DIR = Path(__file__).parent / "static"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Telegram initData validation ──────────────────────────────────────────────

def validate_init_data(init_data: str) -> dict | None:
    try:
        parsed: dict[str, str] = {}
        for item in unquote(init_data).split("&"):
            if "=" in item:
                k, v = item.split("=", 1)
                parsed[k] = v
        hash_value = parsed.pop("hash", None)
        if not hash_value:
            return None
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(hash_value, expected):
            return None
        user_str = parsed.get("user")
        return json.loads(user_str) if user_str else None
    except Exception:
        return None


# ── REST API handlers ─────────────────────────────────────────────────────────

async def api_status(request: web.Request) -> web.Response:
    total = await db.get_total()
    donors = await db.get_donor_count()
    now = datetime.now(timezone.utc)
    secs = max(int((DEADLINE - now).total_seconds()), 0)
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    return web.json_response({
        "total": total,
        "goal": GOAL,
        "donors": donors,
        "pct": round(min(total / GOAL * 100, 9999), 1),
        "goal_reached": total >= GOAL,
        "countdown": {"days": days, "hours": hours, "minutes": minutes, "seconds": seconds},
    })


async def api_leaderboard(request: web.Request) -> web.Response:
    rows = await db.get_leaderboard()
    return web.json_response([
        {"name": r[0], "username": r[1], "amount": r[2]} for r in rows
    ])


async def api_my_pledge(request: web.Request) -> web.Response:
    init_data = request.query.get("initData", "")
    user = validate_init_data(init_data)
    amount = await db.get_pledge(user["id"]) if user else None
    return web.json_response({"amount": amount})


async def api_pledge(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    user = validate_init_data(body.get("initData", ""))
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    amount = body.get("amount")
    if not isinstance(amount, int) or amount < 50:
        return web.json_response({"error": "Minimum amount is 50 RSD"}, status=400)
    await db.upsert_pledge(user["id"], user.get("username"), user.get("first_name", ""), amount)
    total = await db.get_total()
    donors = await db.get_donor_count()
    return web.json_response({
        "ok": True, "total": total, "donors": donors, "goal_reached": total >= GOAL,
    })


async def api_remove_pledge(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    user = validate_init_data(body.get("initData", ""))
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    await db.remove_pledge(user["id"])
    return web.json_response({"ok": True})


async def serve_index(request: web.Request) -> web.Response:
    return web.FileResponse(STATIC_DIR / "index.html")


# ── Telegram webhook ──────────────────────────────────────────────────────────

async def webhook_handler(request: web.Request) -> web.Response:
    ptb_app: Application = request.app["ptb_app"]
    try:
        data = await request.json()
        update = Update.de_json(data, ptb_app.bot)
        await ptb_app.process_update(update)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    return web.Response(text="ok")


# ── Bot commands ──────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = WEBHOOK_URL or "https://example.com"
    await update.message.reply_text(
        "💈 *Bald Ilia Campaign*\n\n"
        "We're raising *30,000 RSD* to shave Ilia's head! 🧑‍🦲\n\n"
        "Open the app below to pledge and track progress:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🪒 Open App", web_app=WebAppInfo(url=url))]
        ]),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = WEBHOOK_URL or "https://example.com"
    await update.message.reply_text(
        "🪒 *Bald Ilia — Help*\n\n"
        "🎯 Goal: *30,000 RSD*\n"
        "📅 Deadline: *August 29, 2026*\n\n"
        "If we collect enough — Ilia shaves his head! 💈",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🪒 Open App", web_app=WebAppInfo(url=url))]
        ]),
    )


# ── Entry point ───────────────────────────────────────────────────────────────

async def run():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set.")

    await db.init_db()
    logger.info("Database initialized.")

    ptb_app = Application.builder().token(BOT_TOKEN).build()
    ptb_app.add_handler(CommandHandler("start", cmd_start))
    ptb_app.add_handler(CommandHandler("help", cmd_help))

    aio_app = web.Application()
    aio_app["ptb_app"] = ptb_app
    aio_app.router.add_post("/webhook", webhook_handler)
    aio_app.router.add_get("/api/status", api_status)
    aio_app.router.add_get("/api/leaderboard", api_leaderboard)
    aio_app.router.add_get("/api/my-pledge", api_my_pledge)
    aio_app.router.add_post("/api/pledge", api_pledge)
    aio_app.router.add_post("/api/remove-pledge", api_remove_pledge)
    aio_app.router.add_get("/", serve_index)

    async with ptb_app:
        await ptb_app.initialize()
        await ptb_app.start()

        if WEBHOOK_URL:
            await ptb_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
            try:
                await ptb_app.bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(
                        text="Open App",
                        web_app=WebAppInfo(url=WEBHOOK_URL),
                    )
                )
                logger.info("Menu button set.")
            except Exception as e:
                logger.warning(f"Could not set menu button: {e}")

        runner = web.AppRunner(aio_app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", PORT).start()
        logger.info(f"Server running on port {PORT}.")

        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()
            await ptb_app.stop()


if __name__ == "__main__":
    asyncio.run(run())
