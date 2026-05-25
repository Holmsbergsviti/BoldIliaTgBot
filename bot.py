import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import database as db

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://boldilia-bot.onrender.com
PORT = int(os.getenv("PORT", 8080))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

GOAL = 30_000          # Serbian dinars
DEADLINE = datetime(2026, 8, 29, tzinfo=timezone.utc)

PRESET_AMOUNTS = [200, 500, 1_000, 2_000, 5_000, 10_000]

# ConversationHandler state
WAITING_CUSTOM = 1

# ── Formatting helpers ───────────────────────────────────────────────────────

def fmt(n: int) -> str:
    """Format number with Serbian thousands separator (.)."""
    return f"{n:,}".replace(",", ".")


def progress_bar(total: int, goal: int = GOAL, width: int = 20) -> str:
    pct = min(total / goal, 1.0)
    filled = round(pct * width)
    bar = "█" * filled + "░" * (width - filled)
    over_goal = total > goal
    emoji = "🔥" if over_goal else "📊"
    return f"{emoji} [{bar}] {pct*100:.1f}%"


def countdown_text() -> str:
    now = datetime.now(timezone.utc)
    delta = DEADLINE - now
    if delta.total_seconds() <= 0:
        return "⌛ Rok je istekao!"
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes = rem // 60
    return f"⏳ Do 29. avgusta: *{days}* dana, *{hours}h {minutes}min*"


def status_text(total: int, donors: int) -> str:
    over = total >= GOAL
    header = (
        "🪒✨ *MISIJA: ĆELAVOST* ✨🪒\n\n"
        "Skupljamo pare da Ilija obrije glavu! 😈\n"
    )
    bar = progress_bar(total)
    amounts = (
        f"\n💰 Skupljeno: *{fmt(total)} RSD*\n"
        f"🎯 Cilj:      *{fmt(GOAL)} RSD*\n"
        f"👥 Donatori:  *{donors}*\n"
    )
    extra = ""
    if over:
        surplus = total - GOAL
        extra = (
            f"\n🔥🔥🔥 *CILJ DOSTIGNUT!* 🔥🔥🔥\n"
            f"Čak *{fmt(surplus)} RSD* iznad cilja!\n"
            "Ilija, mašina čeka! 💈\n"
        )
    countdown = "\n" + countdown_text()
    return header + bar + amounts + extra + countdown


# ── /start ───────────────────────────────────────────────────────────────────

INTRO_FRAMES = [
    "💈",
    "💈 *Učitavanje operacije...*",
    "💈 *Učitavanje operacije...*\n✂️",
    "💈 *Učitavanje operacije...*\n✂️ _Oštrenje mašinice..._",
    (
        "╔══════════════════════╗\n"
        "║  🪒  ĆELAVI ILIJA  🪒  ║\n"
        "╚══════════════════════╝\n\n"
        "Pozdrav! 👋\n\n"
        "Skupljamo *{goal} RSD* da Ilija obrije glavu do gole kože! 🧑‍🦲\n\n"
        "Ako cilj bude dostignut do *29. avgusta*, mašinica kreće! 💈\n\n"
        "Odaberi koliko si spreman/na da daš, i pomozi misiji! 😈"
    ),
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("💈", parse_mode=ParseMode.MARKDOWN)
    for i, frame in enumerate(INTRO_FRAMES[1:], 1):
        await asyncio.sleep(0.7)
        text = frame.format(goal=fmt(GOAL)) if "{goal}" in frame else frame
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)

    keyboard = [
        [InlineKeyboardButton("💸 Daj pare!", callback_data="pledge")],
        [InlineKeyboardButton("📊 Status kampanje", callback_data="status")],
        [InlineKeyboardButton("🏆 Rang lista", callback_data="leaderboard")],
    ]
    await asyncio.sleep(1.0)
    await update.message.reply_text(
        "Šta želiš da uradiš?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── /pledge & pledge flow ────────────────────────────────────────────────────

def pledge_keyboard(current: int | None = None) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for i, amt in enumerate(PRESET_AMOUNTS):
        marker = " ✅" if amt == current else ""
        row.append(InlineKeyboardButton(f"{fmt(amt)} RSD{marker}", callback_data=f"amt_{amt}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✏️ Unesi drugi iznos", callback_data="amt_custom")])
    if current:
        rows.append([InlineKeyboardButton("❌ Poništi moje učešće", callback_data="remove_pledge")])
    rows.append([InlineKeyboardButton("🔙 Nazad", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


async def pledge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    current = await db.get_pledge(user.id)
    intro = (
        "💸 *Odaberi iznos koji si spreman/na da doniraš:*\n\n"
        "_Ovo je tvoje obećanje — pare se skupljaju kad Ilija obrije glavu!_\n"
    )
    if current:
        intro += f"\n🔄 Tvoja trenutna uplata: *{fmt(current)} RSD*\n"
    await update.message.reply_text(
        intro,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=pledge_keyboard(current),
    )


async def pledge_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if query.data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("💸 Daj pare!", callback_data="pledge")],
            [InlineKeyboardButton("📊 Status kampanje", callback_data="status")],
            [InlineKeyboardButton("🏆 Rang lista", callback_data="leaderboard")],
        ]
        await query.edit_message_text(
            "Šta želiš da uradiš?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return ConversationHandler.END

    if query.data == "pledge":
        current = await db.get_pledge(user.id)
        intro = (
            "💸 *Odaberi iznos koji si spreman/na da doniraš:*\n\n"
            "_Ovo je tvoje obećanje — pare se skupljaju kad Ilija obrije glavu!_\n"
        )
        if current:
            intro += f"\n🔄 Tvoja trenutna uplata: *{fmt(current)} RSD*\n"
        await query.edit_message_text(
            intro,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=pledge_keyboard(current),
        )
        return

    if query.data == "remove_pledge":
        await db.remove_pledge(user.id)
        await query.edit_message_text(
            "❌ Tvoje učešće je poništeno.\n\nMožeš se uvek prijaviti ponovo! 💸",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Glavni meni", callback_data="main_menu")]
            ]),
        )
        return ConversationHandler.END

    if query.data == "status":
        total = await db.get_total()
        donors = await db.get_donor_count()
        await query.edit_message_text(
            status_text(total, donors),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💸 Daj pare!", callback_data="pledge")],
                [InlineKeyboardButton("🏆 Rang lista", callback_data="leaderboard")],
                [InlineKeyboardButton("🔙 Nazad", callback_data="main_menu")],
            ]),
        )
        return

    if query.data == "leaderboard":
        rows = await db.get_leaderboard()
        total = await db.get_total()
        medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
        lines = ["🏆 *TOP DONATORI* 🏆\n"]
        for i, (fname, uname, amt) in enumerate(rows):
            display = f"@{uname}" if uname else fname
            lines.append(f"{medals[i]} {display} — *{fmt(amt)} RSD*")
        lines.append(f"\n💰 Ukupno skupljeno: *{fmt(total)} RSD* / {fmt(GOAL)} RSD")
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💸 Daj pare!", callback_data="pledge")],
                [InlineKeyboardButton("🔙 Nazad", callback_data="main_menu")],
            ]),
        )
        return

    if query.data.startswith("amt_"):
        val = query.data[4:]
        if val == "custom":
            await query.edit_message_text(
                "✏️ Unesi iznos u dinarima (samo broj, npr. *3000*):",
                parse_mode=ParseMode.MARKDOWN,
            )
            return WAITING_CUSTOM
        amount = int(val)
        await _confirm_pledge(query, user, amount)
        return ConversationHandler.END


async def _confirm_pledge(query, user, amount: int):
    name = user.first_name
    await db.upsert_pledge(user.id, user.username, user.first_name, amount)
    total = await db.get_total()
    donors = await db.get_donor_count()
    over = total >= GOAL
    congrats = ""
    if over:
        congrats = "\n\n🔥🔥🔥 *CILJ JE DOSTIGNUT!* Ilija, mašinica te čeka! 🔥🔥🔥"
    bar = progress_bar(total)
    text = (
        f"✅ *Hvala, {name}!*\n\n"
        f"Tvoja uplata: *{fmt(amount)} RSD* 💸\n\n"
        f"{bar}\n"
        f"Skupljeno: *{fmt(total)} RSD* / *{fmt(GOAL)} RSD*\n"
        f"Donatori: *{donors}*"
        f"{congrats}"
    )
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Status kampanje", callback_data="status")],
            [InlineKeyboardButton("🏆 Rang lista", callback_data="leaderboard")],
            [InlineKeyboardButton("🔙 Glavni meni", callback_data="main_menu")],
        ]),
    )


async def custom_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(".", "").replace(",", "").replace(" ", "")
    try:
        amount = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ Neispravan unos. Molim unesi samo broj (npr. *3000*).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return WAITING_CUSTOM

    if amount < 50:
        await update.message.reply_text(
            "❌ Minimalni iznos je *50 RSD*. Pokušaj ponovo.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return WAITING_CUSTOM

    user = update.effective_user
    await db.upsert_pledge(user.id, user.username, user.first_name, amount)
    total = await db.get_total()
    donors = await db.get_donor_count()
    over = total >= GOAL
    congrats = ""
    if over:
        congrats = "\n\n🔥🔥🔥 *CILJ JE DOSTIGNUT!* Ilija, mašinica te čeka! 🔥🔥🔥"
    bar = progress_bar(total)
    await update.message.reply_text(
        f"✅ *Hvala, {user.first_name}!*\n\n"
        f"Tvoja uplata: *{fmt(amount)} RSD* 💸\n\n"
        f"{bar}\n"
        f"Skupljeno: *{fmt(total)} RSD* / *{fmt(GOAL)} RSD*\n"
        f"Donatori: *{donors}*"
        f"{congrats}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Status kampanje", callback_data="status")],
            [InlineKeyboardButton("🏆 Rang lista", callback_data="leaderboard")],
            [InlineKeyboardButton("🔙 Glavni meni", callback_data="main_menu")],
        ]),
    )
    return ConversationHandler.END


# ── /status ──────────────────────────────────────────────────────────────────

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📡 _Učitavam podatke..._", parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(0.8)

    total = await db.get_total()
    donors = await db.get_donor_count()

    # Animated progress reveal
    pct = min(total / GOAL, 1.0)
    steps = 8
    for step in range(1, steps + 1):
        partial_total = int(total * (step / steps))
        bar = progress_bar(partial_total)
        await msg.edit_text(
            f"📡 *Učitavam...*\n\n{bar}\n_{fmt(partial_total)} RSD_",
            parse_mode=ParseMode.MARKDOWN,
        )
        await asyncio.sleep(0.15)

    await msg.edit_text(
        status_text(total, donors),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 Daj pare!", callback_data="pledge")],
            [InlineKeyboardButton("🏆 Rang lista", callback_data="leaderboard")],
        ]),
    )


# ── /leaderboard ─────────────────────────────────────────────────────────────

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🏆 _Učitavam rang listu..._", parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(0.6)

    rows = await db.get_leaderboard()
    total = await db.get_total()

    if not rows:
        await msg.edit_text(
            "😔 Još nema donatora. Budi prvi! /pledge",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    lines = ["🏆 *TOP DONATORI* 🏆\n"]

    # Reveal donors one by one
    for i, (fname, uname, amt) in enumerate(rows):
        display = f"@{uname}" if uname else fname
        lines.append(f"{medals[i]} {display} — *{fmt(amt)} RSD*")
        await msg.edit_text(
            "\n".join(lines) + "\n\n_..._",
            parse_mode=ParseMode.MARKDOWN,
        )
        await asyncio.sleep(0.3)

    lines.append(f"\n💰 Ukupno skupljeno: *{fmt(total)} RSD* / {fmt(GOAL)} RSD")
    lines.append(countdown_text())
    await msg.edit_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 Daj pare!", callback_data="pledge")],
            [InlineKeyboardButton("📊 Status kampanje", callback_data="status")],
        ]),
    )


# ── /countdown ───────────────────────────────────────────────────────────────

async def countdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc)
    delta = DEADLINE - now
    days = max(delta.days, 0)

    # Hair emoji string that shrinks with fewer days remaining
    total_days = (DEADLINE - datetime(2026, 5, 25, tzinfo=timezone.utc)).days
    hair_count = max(1, round(20 * (days / total_days))) if total_days > 0 else 1
    hair = "👱" * hair_count

    msg = await update.message.reply_text(
        f"💈 _Brije se..._\n\n{hair}",
        parse_mode=ParseMode.MARKDOWN,
    )
    await asyncio.sleep(1.0)

    frames = []
    for i in range(hair_count, -1, -max(1, hair_count // 6)):
        frames.append("👱" * max(i, 0))
    frames.append("🧑‍🦲")

    for frame in frames:
        await asyncio.sleep(0.5)
        await msg.edit_text(
            f"💈 _Brije se..._\n\n{frame or '🧑‍🦲'}",
            parse_mode=ParseMode.MARKDOWN,
        )

    await asyncio.sleep(0.5)
    await msg.edit_text(
        f"💈 *ODBROJAVANJE DO ĆELAVOSTI* 💈\n\n"
        f"🧑‍🦲 Ilija ostaje bez kose za...\n\n"
        f"*{days}* dana\n\n"
        f"{countdown_text()}\n\n"
        f"📅 Datum: *29. avgust 2026.*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 Daj pare!", callback_data="pledge")],
            [InlineKeyboardButton("📊 Status kampanje", callback_data="status")],
        ]),
    )


# ── /help ────────────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🪒 *ĆELAVI ILIJA — POMOĆ* 🪒\n\n"
        "/start — Početni ekran\n"
        "/pledge — Prijavi se kao donator\n"
        "/status — Pogledaj napredak kampanje\n"
        "/leaderboard — Rang lista donatora\n"
        "/countdown — Odbrojavanje do 29. avgusta\n"
        "/help — Ova poruka\n\n"
        f"🎯 Cilj: *{fmt(GOAL)} RSD*\n"
        "Ako skupimo dovoljno — Ilija brije glavu! 💈",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Main ─────────────────────────────────────────────────────────────────────

async def post_init(app: Application):
    await db.init_db()
    logger.info("Database initialized.")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Copy .env.example to .env and add your token.")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    pledge_conv = ConversationHandler(
        entry_points=[
            CommandHandler("pledge", pledge_command),
            CallbackQueryHandler(pledge_button, pattern="^(pledge|amt_.+|remove_pledge|main_menu|status|leaderboard)$"),
        ],
        states={
            WAITING_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_amount_received)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("countdown", countdown_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(pledge_conv)

    if WEBHOOK_URL:
        logger.info(f"Bot started in webhook mode on port {PORT}.")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="/webhook",
            webhook_url=f"{WEBHOOK_URL}/webhook",
        )
    else:
        logger.info("Bot started in polling mode.")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
