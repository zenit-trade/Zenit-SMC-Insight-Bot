import datetime as dt
import pytz
from sqlalchemy import and_
from models import SessionLocal, Trade, Status

IST = pytz.timezone("Asia/Kolkata")


def _ist_day_bounds(days_ago: int = 0):
    """Return (start_utc, end_utc) for a given IST calendar day."""
    now_ist = dt.datetime.now(IST)
    target = now_ist - dt.timedelta(days=days_ago)
    start_ist = IST.localize(dt.datetime(target.year, target.month, target.day))
    end_ist = start_ist + dt.timedelta(days=1)
    return start_ist.astimezone(pytz.utc).replace(tzinfo=None), end_ist.astimezone(pytz.utc).replace(tzinfo=None)


def get_stats(start_utc: dt.datetime, end_utc: dt.datetime):
    session = SessionLocal()
    try:
        trades = session.query(Trade).filter(
            and_(Trade.created_at >= start_utc, Trade.created_at < end_utc)
        ).all()

        tp_hits = [t for t in trades if t.status == Status.TP_HIT]
        sl_hits = [t for t in trades if t.status == Status.SL_HIT]
        open_trades = [t for t in trades if t.status == Status.OPEN]
        closed = len(tp_hits) + len(sl_hits)
        win_rate = (len(tp_hits) / closed * 100) if closed else 0.0

        return {
            "total": len(trades),
            "tp_hits": len(tp_hits),
            "sl_hits": len(sl_hits),
            "open": len(open_trades),
            "win_rate": round(win_rate, 1),
            "trades": trades,
        }
    finally:
        session.close()


def stats_for_today():
    start, end = _ist_day_bounds(0)
    return get_stats(start, end)


def stats_for_yesterday():
    start, end = _ist_day_bounds(1)
    return get_stats(start, end)


def stats_for_last_n_days(n: int = 7):
    start, _ = _ist_day_bounds(n - 1)
    _, end = _ist_day_bounds(0)
    return get_stats(start, end)


def format_stats_message(title: str, stats: dict) -> str:
    lines = [
        f"*{title}*",
        f"Total signals: {stats['total']}",
        f"✅ TP hits: {stats['tp_hits']}",
        f"❌ SL hits: {stats['sl_hits']}",
        f"⏳ Still open: {stats['open']}",
        f"🏆 Win rate: {stats['win_rate']}%",
    ]
    return "\n".join(lines)


def format_compare_message(today: dict, yesterday: dict) -> str:
    lines = [
        "*📊 Yesterday vs Today*",
        "",
        "*Yesterday*",
        f"TP: {yesterday['tp_hits']} | SL: {yesterday['sl_hits']} | Win rate: {yesterday['win_rate']}%",
        "",
        "*Today*",
        f"TP: {today['tp_hits']} | SL: {today['sl_hits']} | Win rate: {today['win_rate']}%",
    ]
    delta = today["win_rate"] - yesterday["win_rate"]
    arrow = "📈" if delta > 0 else ("📉" if delta < 0 else "➖")
    lines.append("")
    lines.append(f"{arrow} Win rate change: {delta:+.1f}%")
    return "\n".join(lines)
