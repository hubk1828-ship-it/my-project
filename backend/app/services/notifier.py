"""
CryptoAnalyzer — Notification Service
Sends alerts via Telegram and Email with deduplication.
"""

import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib
try:
    from telegram import Bot
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import get_settings
from app.models.notification import Notification, UserNotificationPreference

settings = get_settings()
logger = logging.getLogger(__name__)

# Deduplication cache: {(user_id, message_hash): last_sent_time}
_sent_cache: dict = {}
DEDUP_WINDOW = timedelta(minutes=30)


def _dedup_key(user_id: str, message: str) -> str:
    return f"{user_id}:{hash(message)}"


def _should_send(user_id: str, message: str) -> bool:
    key = _dedup_key(user_id, message)
    last_sent = _sent_cache.get(key)
    if last_sent and datetime.now(timezone.utc) - last_sent < DEDUP_WINDOW:
        return False
    _sent_cache[key] = datetime.now(timezone.utc)
    return True


# ===== Telegram =====

async def send_telegram(chat_id: str, message: str) -> bool:
    """Send message via Telegram Bot."""
    if not HAS_TELEGRAM or not settings.TELEGRAM_BOT_TOKEN or not chat_id:
        logger.warning("Telegram not configured")
        return False
    try:
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


# ===== Email =====

async def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send email via SMTP."""
    if not settings.SMTP_USER:
        logger.warning("SMTP not configured")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            start_tls=True,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
        )
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


# ===== Alert Templates =====

def format_opportunity_alert(symbol: str, decision: str, price: float, reasoning: str) -> dict:
    emoji = "🟢" if decision == "buy" else "🔴" if decision == "sell" else "⚪"
    action = "شراء" if decision == "buy" else "بيع" if decision == "sell" else "لا فرصة"

    telegram_msg = (
        f"{emoji} <b>فرصة {action}</b>\n\n"
        f"💎 العملة: <b>{symbol}</b>\n"
        f"💰 السعر: <b>${price:,.2f}</b>\n\n"
        f"📋 السبب:\n{reasoning}"
    )

    email_html = f"""
    <div style="font-family:Arial; max-width:500px; margin:0 auto; direction:rtl;">
        <h2 style="color:{'#10b981' if decision == 'buy' else '#ef4444'};">{emoji} فرصة {action}</h2>
        <p><strong>العملة:</strong> {symbol}</p>
        <p><strong>السعر:</strong> ${price:,.2f}</p>
        <p><strong>السبب:</strong></p>
        <pre style="background:#f3f4f6;padding:12px;border-radius:8px;">{reasoning}</pre>
    </div>
    """

    return {"telegram": telegram_msg, "email_html": email_html, "email_subject": f"{emoji} فرصة {action}: {symbol}"}


def format_trade_executed_alert(symbol: str, side: str, qty: float, price: float, total: float) -> dict:
    emoji = "✅" if side == "buy" else "📤"
    action = "شراء" if side == "buy" else "بيع"

    telegram_msg = (
        f"{emoji} <b>تم تنفيذ صفقة</b>\n\n"
        f"💎 {symbol}\n"
        f"📊 النوع: {action}\n"
        f"📦 الكمية: {qty}\n"
        f"💰 السعر: ${price:,.2f}\n"
        f"💵 القيمة: ${total:,.2f}"
    )

    return {"telegram": telegram_msg, "email_html": f"<p>{telegram_msg}</p>", "email_subject": f"{emoji} صفقة {action}: {symbol}"}


def format_trade_failed_alert(symbol: str, error: str) -> dict:
    telegram_msg = f"❌ <b>فشل تنفيذ صفقة</b>\n\n💎 {symbol}\n⚠️ السبب: {error}"
    return {"telegram": telegram_msg, "email_html": f"<p>{telegram_msg}</p>", "email_subject": f"❌ فشل صفقة: {symbol}"}


def format_daily_report(
    balance: float, daily_pnl: float, pnl_pct: float,
    total_trades: int, bot_trades: int, manual_trades: int,
    no_opp_count: int, best_trade: str, worst_trade: str,
    date: str,
) -> dict:
    telegram_msg = (
        f"📊 <b>تقرير يومي</b> — {date}\n\n"
        f"💰 الرصيد: <b>${balance:,.2f}</b>\n"
        f"📈 ربح اليوم: <b>{'+'if daily_pnl>=0 else ''}{daily_pnl:,.2f} ({pnl_pct:+.1f}%)</b>\n\n"
        f"🔄 صفقات منفّذة: <b>{total_trades}</b>\n"
        f"   ├ 🤖 آلية: {bot_trades}\n"
        f"   └ 👤 يدوية: {manual_trades}\n\n"
        f"🏆 أفضل صفقة: {best_trade}\n"
        f"📉 أسوأ صفقة: {worst_trade}\n\n"
        f"⚠️ قرارات «لا فرصة»: <b>{no_opp_count} عملات</b>"
    )

    return {"telegram": telegram_msg, "email_html": f"<pre>{telegram_msg}</pre>", "email_subject": f"📊 تقرير يومي — {date}"}


# ===== Main Send Function =====

async def send_notification(
    user_id: str,
    notification_type: str,  # opportunity | trade_executed | trade_failed | daily_summary
    content: dict,
    db: AsyncSession,
):
    """Send notification via user's preferred channels with deduplication."""
    # Get user preferences
    result = await db.execute(
        select(UserNotificationPreference).where(UserNotificationPreference.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        return

    message = content.get("telegram", "")

    # Check dedup
    if not _should_send(user_id, message):
        logger.info(f"Skipping duplicate notification for user {user_id}")
        return

    # Check if user wants this type
    if notification_type == "opportunity" and not prefs.notify_opportunities:
        return
    if notification_type in ("trade_executed", "trade_failed") and not prefs.notify_trades:
        return
    if notification_type == "daily_summary" and not prefs.notify_daily_summary:
        return

    sent_via = []

    # Telegram
    if prefs.telegram_enabled and prefs.telegram_chat_id:
        success = await send_telegram(prefs.telegram_chat_id, message)
        if success:
            sent_via.append("telegram")

    # Email (use user's email from User model)
    if prefs.email_enabled:
        from app.models.user import User
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user:
            success = await send_email(
                user.email,
                content.get("email_subject", "CryptoAnalyzer Alert"),
                content.get("email_html", message),
            )
            if success:
                sent_via.append("email")

    # Save notification record
    for channel in sent_via:
        notif = Notification(
            user_id=user_id,
            type=channel,
            category=notification_type,
            title=content.get("email_subject", ""),
            message=message[:1000],
            is_sent=True,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(notif)

    await db.flush()
