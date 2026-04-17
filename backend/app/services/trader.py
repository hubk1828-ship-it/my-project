"""
CryptoAnalyzer — Auto Trading Service
Executes trades based on analysis decisions within user-defined limits.
"""

import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.trade import Trade, BotSettings
from app.models.wallet import Wallet
from app.models.analysis import BotAnalysis
from app.core.security import decrypt_api_key
from app.services.binance_client import BinanceClient

logger = logging.getLogger(__name__)


async def check_trade_limits(
    user_id: str,
    bot_settings: BotSettings,
    trade_amount_usdt: float,
    total_balance_usdt: float,
    db: AsyncSession,
) -> dict:
    """Check all trading limits before executing."""
    errors = []

    # 1. Auto trade enabled + admin approved
    if not bot_settings.is_auto_trade_enabled:
        errors.append("التداول الآلي غير مفعّل")
    if not bot_settings.is_admin_approved:
        errors.append("التداول الآلي لم يوافق عليه الأدمن")

    # 2. Daily trade count
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(Trade.id)).where(
            Trade.user_id == user_id,
            Trade.executed_by == "bot",
            Trade.created_at >= today_start,
            Trade.status == "filled",
        )
    )
    today_trades = result.scalar() or 0
    if today_trades >= bot_settings.max_trades_per_day:
        errors.append(f"تم الوصول للحد اليومي: {bot_settings.max_trades_per_day} صفقات")

    # 3. Trade amount within limits
    if trade_amount_usdt > float(bot_settings.max_trade_amount):
        errors.append(f"قيمة الصفقة ${trade_amount_usdt} تتجاوز الحد ${bot_settings.max_trade_amount}")

    # 4. Portfolio percentage
    max_allowed = total_balance_usdt * float(bot_settings.max_portfolio_percentage) / 100
    if trade_amount_usdt > max_allowed:
        errors.append(f"الصفقة تتجاوز {bot_settings.max_portfolio_percentage}% من المحفظة")

    # 5. Daily loss limit
    result = await db.execute(
        select(func.sum(Trade.total_value)).where(
            Trade.user_id == user_id,
            Trade.executed_by == "bot",
            Trade.created_at >= today_start,
            Trade.status == "filled",
            Trade.side == "sell",
        )
    )
    # Simplified: check if we've hit daily loss (actual P&L requires more complex calculation)
    daily_loss = result.scalar() or 0

    # 6. Min/Max loss limits
    if daily_loss > float(bot_settings.max_loss_limit):
        errors.append(f"تجاوزت الحد الأعلى للخسارة: ${bot_settings.max_loss_limit}")

    return {
        "can_trade": len(errors) == 0,
        "errors": errors,
        "today_trades": today_trades,
    }


async def execute_auto_trade(
    user_id: str,
    wallet: Wallet,
    analysis: BotAnalysis,
    trade_amount_usdt: float,
    db: AsyncSession,
) -> dict:
    """Execute a single auto trade on Binance."""
    try:
        api_key = decrypt_api_key(wallet.api_key_encrypted)
        api_secret = decrypt_api_key(wallet.api_secret_encrypted)
        client = BinanceClient(api_key, api_secret)

        # Get current price
        current_price = await client.get_ticker_price(analysis.symbol)

        # Place market order
        side = "BUY" if analysis.decision == "buy" else "SELL"
        order_result = await client.place_order(
            symbol=analysis.symbol,
            side=side,
            order_type="MARKET",
            quote_order_qty=trade_amount_usdt if side == "BUY" else None,
            quantity=round(trade_amount_usdt / current_price, 6) if side == "SELL" else None,
        )

        # Calculate filled values
        filled_qty = float(order_result.get("executedQty", 0))
        filled_price = float(order_result.get("fills", [{}])[0].get("price", current_price)) if order_result.get("fills") else current_price
        total_value = filled_qty * filled_price
        fee = sum(float(f.get("commission", 0)) for f in order_result.get("fills", []))

        # Save trade record
        trade = Trade(
            user_id=user_id,
            wallet_id=wallet.id,
            analysis_id=analysis.id,
            symbol=analysis.symbol,
            side=analysis.decision,
            order_type="market",
            quantity=filled_qty,
            price=filled_price,
            total_value=total_value,
            fee=fee,
            status="filled",
            executed_by="bot",
            exchange_order_id=str(order_result.get("orderId", "")),
            executed_at=datetime.now(timezone.utc),
        )
        db.add(trade)
        await db.flush()

        logger.info(f"Auto trade executed: {side} {analysis.symbol} qty={filled_qty} price={filled_price}")

        return {
            "success": True,
            "trade_id": trade.id,
            "symbol": analysis.symbol,
            "side": analysis.decision,
            "quantity": filled_qty,
            "price": filled_price,
            "total_value": total_value,
        }

    except Exception as e:
        # Log failed trade
        trade = Trade(
            user_id=user_id,
            wallet_id=wallet.id,
            analysis_id=analysis.id,
            symbol=analysis.symbol,
            side=analysis.decision,
            order_type="market",
            quantity=0,
            price=0,
            total_value=0,
            status="failed",
            executed_by="bot",
            error_message=str(e)[:500],
        )
        db.add(trade)
        await db.flush()

        logger.error(f"Auto trade failed for {analysis.symbol}: {e}")
        return {
            "success": False,
            "error": str(e),
            "symbol": analysis.symbol,
        }
