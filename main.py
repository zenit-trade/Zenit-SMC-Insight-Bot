import os
import logging
import datetime as dt

from fastapi import FastAPI, Request, HTTPException
from telegram import Update, Bot
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes
from sqlalchemy.exc import IntegrityError

from models import init_db, SessionLocal, Trade, Direction, Status
import analytics

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("zenit-analytics-bot")

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]  # where live trade alerts get pushed
WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")  # optional shared secret
APP_URL = os.environ["APP_URL"]  # e.g. https://your-app.up.railway.app (Railway public domain)

app = FastAPI()
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
bot = Bot(token=TELEGRAM_TOKEN)


async def safe_send(text: str, parse_mode: str = "HTML"):
    """Send a Telegram message without letting delivery failures (bot
    blocked, chat deleted, rate limits, etc.) crash the webhook handler.
    The trade is still logged in the DB either way — this only affects
    the notification, not the trade record."""
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode=parse_mode)
    except TelegramError as e:
        log.warning("Telegram delivery failed (%s) — continuing anyway: %s", type(e).__name__, e)


# ---------- Telegram commands ----------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Zenit Trade Analytics Bot online.\n\n"
        "/analyze — today's stats\n"
        "/analyze weekly — last 7 days\n"
        "/compare — yesterday vs today"
    )


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].lower() == "weekly":
        stats = analytics.stats_for_last_n_days(7)
        msg = analytics.format_stats_message("📅 Last 7 Days", stats)
    else:
        stats = analytics.stats_for_today()
        msg = analytics.format_stats_message("📆 Today", stats)
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_compare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = analytics.stats_for_today()
    yesterday = analytics.stats_for_yesterday()
    msg = analytics.format_compare_message(today, yesterday)
    await update.message.reply_text(msg, parse_mode="Markdown")


telegram_app.add_handler(CommandHandler("start", cmd_start))
telegram_app.add_handler(CommandHandler("analyze", cmd_analyze))
telegram_app.add_handler(CommandHandler("compare", cmd_compare))


# ---------- FastAPI lifecycle ----------

@app.on_event("startup")
async def startup():
    init_db()
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(url=f"{APP_URL}/webhook/telegram/{TELEGRAM_TOKEN}")
    await telegram_app.start()
    log.info("Telegram webhook set and bot started.")


@app.on_event("shutdown")
async def shutdown():
    await telegram_app.stop()
    await telegram_app.shutdown()


# ---------- Telegram webhook endpoint ----------

@app.post("/webhook/telegram/{token}")
async def telegram_webhook(token: str, request: Request):
    if token != TELEGRAM_TOKEN:
        raise HTTPException(status_code=403, detail="bad token")
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}


# ---------- TradingView webhook endpoint ----------

@app.post("/webhook/tradingview")
async def tradingview_webhook(request: Request):
    payload = await request.json()
    log.info("Received TradingView payload: %s", payload)

    if WEBHOOK_SECRET and payload.get("secret") != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="bad secret")

    alert_type = payload.get("type")
    signal_id = payload.get("signal_id")
    # The Pine script already builds a nicely formatted HTML message (same
    # text it would have sent straight to Telegram) — forward that as-is
    # instead of re-composing it here, so the two stay in sync automatically.
    pine_text = payload.get("text")

    session = SessionLocal()
    try:
        if alert_type == "SETUP_INCOMING":
            # Informational only — nothing to log, just forward to Telegram.
            if pine_text:
                await safe_send(pine_text)
            return {"ok": True}

        if not signal_id:
            raise HTTPException(status_code=400, detail="signal_id is required for this alert type")

        if alert_type == "ENTRY":
            # TradingView retries webhook deliveries that appear to have
            # failed (timeouts, transient errors, etc). That means the SAME
            # signal_id can legitimately arrive more than once. Treat that
            # as a no-op instead of crashing: check first, and also guard
            # the insert itself against a race between the check and the
            # commit (two near-simultaneous retries).
            existing = session.query(Trade).filter(Trade.signal_id == signal_id).first()
            if existing:
                log.info("Duplicate ENTRY for signal_id=%s — resending Telegram message only", signal_id)
                if pine_text:
                    await safe_send(pine_text)
                return {"ok": True, "duplicate": True}

            direction = payload["direction"].upper()
            entry = float(payload["entry"])
            sl = float(payload["sl"])
            tp = float(payload["tp"])
            symbol = payload.get("symbol", "XAUUSD")

            trade = Trade(
                signal_id=signal_id,
                symbol=symbol,
                direction=Direction(direction),
                entry_price=entry,
                sl_price=sl,
                tp_price=tp,
                status=Status.OPEN,
            )
            session.add(trade)
            try:
                session.commit()
            except IntegrityError:
                # Another concurrent retry inserted it a moment ago — fine,
                # the trade is logged either way. Don't crash, just move on.
                session.rollback()
                log.info("Race-condition duplicate insert for signal_id=%s, ignoring", signal_id)

            msg = pine_text or f"⚡ {direction} {symbol}\nEntry: {entry}\nSL: {sl}\nTP: {tp}"
            await safe_send(msg)

        elif alert_type in ("TP_HIT", "SL_HIT"):
            trade = session.query(Trade).filter(Trade.signal_id == signal_id).first()
            if not trade:
                log.warning("No matching OPEN trade for signal_id=%s", signal_id)
                if pine_text:
                    await safe_send(pine_text)
                return {"ok": False, "reason": "no matching trade"}

            if trade.status != Status.OPEN:
                # Already closed by an earlier delivery of this same alert —
                # just resend the Telegram confirmation, don't re-close it.
                log.info("Duplicate %s for already-closed signal_id=%s", alert_type, signal_id)
                if pine_text:
                    await safe_send(pine_text)
                return {"ok": True, "duplicate": True}

            trade.status = Status.TP_HIT if alert_type == "TP_HIT" else Status.SL_HIT
            trade.closed_at = dt.datetime.utcnow()
            trade.exit_price = float(payload.get("exit_price", trade.tp_price if alert_type == "TP_HIT" else trade.sl_price))
            session.commit()

            msg = pine_text or f"{'🎯 TP HIT' if alert_type == 'TP_HIT' else '🛑 SL HIT'}\n{trade.symbol} {trade.direction.value}\nExit: {trade.exit_price}"
            await safe_send(msg)

        else:
            raise HTTPException(status_code=400, detail=f"unknown type: {alert_type}")

        return {"ok": True}
    finally:
        session.close()


@app.get("/")
async def health():
    return {"status": "ok"}
