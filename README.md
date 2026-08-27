# Bald Ilia 💈 — Telegram Fundraising Bot & Mini App

A Telegram bot with an embedded [Mini App](https://core.telegram.org/bots/webapps) that runs a light-hearted crowdfunding campaign: raise a target amount, and if the goal is hit the top donor gets to shave "Ilia's" head. On the deadline, a raffle wheel — weighted by how much each person pledged — spins to pick a shirt winner.

The bot serves both the Telegram webhook and the Mini App web UI from a single `aiohttp` server, and stores pledges in PostgreSQL.

## How it works

- Members open the Mini App from the bot and **pledge** an amount (minimum 50 RSD).
- A live **progress bar, donor count, and countdown** track the campaign against its goal.
- A **leaderboard** ranks donors by pledged amount — the top donor earns the razor.
- When the deadline passes, **`/spin`** picks a shirt-raffle winner. Odds are proportional to pledge size (a bigger pledge = a bigger slice of the wheel), and the result is broadcast to every chat the bot knows about.
- Every request from the Mini App is authenticated by validating Telegram's `initData` with an HMAC-SHA256 signature, so pledges can't be forged.

## Bot commands

| Command  | Description                                        |
| -------- | -------------------------------------------------- |
| `/start` | Intro message + button to open the Mini App        |
| `/help`  | Explains the goal, deadline, and the two prizes    |

## REST API

The `aiohttp` server exposes a small JSON API consumed by the Mini App:

| Endpoint             | Purpose                                       |
| -------------------- | --------------------------------------------- |
| `GET /api/status`    | Total raised, goal, donor count, %, countdown |
| `GET /api/leaderboard` | Ranked list of donors                       |
| `GET /api/my_pledge` | The caller's current pledge                    |
| `POST /api/pledge`   | Create or update a pledge                      |
| `POST /api/remove_pledge` | Remove the caller's pledge                |
| `GET /api/wheel`     | Wheel slices weighted by pledge amount         |
| `GET /api/winner`    | The raffle winner, once chosen                 |
| `POST /api/spin`     | Spin the wheel (only after the deadline)       |

## Tech stack

- **Python 3.12**
- [`python-telegram-bot`](https://python-telegram-bot.org/) 21.6
- `aiohttp` — webhook handling, REST API, and static Mini App hosting
- **PostgreSQL** via `psycopg2`
- `python-dotenv` for configuration

## Project structure

```
bot.py            # Telegram handlers, REST API, webhook, wheel/spin logic
database.py       # PostgreSQL access (pledges, winner, chat ids)
static/           # the Telegram Mini App (index.html + assets)
requirements.txt  # dependencies
render.yaml       # Render deployment config
Procfile          # process definition
runtime.txt       # Python version
.env.example      # example configuration
```

## Setup

1. **Create a bot** with [@BotFather](https://t.me/botfather) and copy the token.
2. **Provision a PostgreSQL database** and grab its connection URL.
3. **Configure the environment** — copy `.env.example` to `.env` and fill in:

   ```env
   BOT_TOKEN=your_telegram_bot_token
   DATABASE_URL=postgresql://user:password@host:5432/dbname
   WEBHOOK_URL=https://your-public-url
   ```

4. **Install and run:**

   ```bash
   pip install -r requirements.txt
   python3 bot.py
   ```

The database tables are created automatically on first run.

## Deployment

The repo is ready to deploy to [Render](https://render.com/) using the included `render.yaml` (a web service running `python3 bot.py`). Set `BOT_TOKEN`, `DATABASE_URL`, and `WEBHOOK_URL` as environment variables in the dashboard. `WEBHOOK_URL` must be the public HTTPS URL of the deployed service so Telegram can reach the webhook and load the Mini App.

## Notes

- Amounts in this project are denominated in RSD.
- The goal and deadline are set as constants in `bot.py` (`GOAL`, `DEADLINE`) — adjust them there to reuse the bot for a different campaign.
