"""
Price Monitor — Real-time target/stop monitoring (every 5 seconds).
Lightweight: uses WebSocket cache only, no external API calls.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.paper_trading import TradeSignal, PaperWallet, PaperHolding, PaperBotSettings
from app.services.binance_client import _price_cache

logger = logging.getLogger("price_monitor")


async def run_price_monitor(db: AsyncSession):
    """Fast monitor — checks WebSocket cached prices against active signals. Every 5 sec."""
    import time as _time
    now = _time.time()

    result = await db.execute(select(TradeSignal).where(TradeSignal.status == "active"))
    active_signals = result.scalars().all()
    if not active_signals:
        return

    closed_count = 0
    for signal in active_signals:
        symbol = signal.symbol
        if symbol not in _price_cache:
            continue
        cached_price, cached_ts = _price_cache[symbol]
        if now - cached_ts > 60:
            continue

        current_price = cached_price
        entry = float(signal.entry_price or 0)
        tp1 = float(signal.target_1 or 0)
        tp2 = float(signal.target_2 or 0)
        tp3 = float(signal.target_3 or 0)
        sl = float(signal.stop_loss or 0)
        if entry <= 0:
            continue

        hit_status = None
        if signal.signal_type == "long":
            if sl > 0 and current_price <= sl:
                hit_status = "stopped"
            elif tp3 > 0 and current_price >= tp3:
                hit_status = "hit_target"
            elif tp2 > 0 and current_price >= tp2:
                hit_status = "hit_target"
            elif tp1 > 0 and current_price >= tp1:
                hit_status = "hit_target"
        elif signal.signal_type == "short":
            if sl > 0 and current_price >= sl:
                hit_status = "stopped"
            elif tp3 > 0 and current_price <= tp3:
                hit_status = "hit_target"
            elif tp2 > 0 and current_price <= tp2:
                hit_status = "hit_target"
            elif tp1 > 0 and current_price <= tp1:
                hit_status = "hit_target"

        if not hit_status and signal.expires_at:
            exp = signal.expires_at
            if hasattr(exp, 'tzinfo') and exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                hit_status = "expired"

        if hit_status:
            signal.status = hit_status
            signal.closed_at = datetime.now(timezone.utc)
            signal.close_price = current_price
            if signal.signal_type == "long":
                pnl_pct = ((current_price - entry) / entry) * 100
            else:
                pnl_pct = ((entry - current_price) / entry) * 100
            signal.pnl_percentage = round(pnl_pct, 2)
            closed_count += 1
            emoji = "T" if hit_status == "hit_target" else "S" if hit_status == "stopped" else "E"
            logger.info(f"{emoji} {symbol} {hit_status} @${current_price:.2f} (entry:${entry:.2f} PnL:{pnl_pct:+.2f}%)")
            await _auto_sell_paper(db, signal, current_price)

    if closed_count > 0:
        await db.commit()


async def run_paper_auto_buy(db: AsyncSession):
    """Auto-buy from active signals."""
    from app.services.paper_trader import execute_paper_trade

    result = await db.execute(select(PaperBotSettings).where(PaperBotSettings.is_enabled == True))
    settings_list = result.scalars().all()
    if not settings_list:
        return

    sig_result = await db.execute(
        select(TradeSignal).where(TradeSignal.status == "active", TradeSignal.signal_type.in_(["long", "short"]))
    )
    active_signals = sig_result.scalars().all()
    if not active_signals:
        return

    bought = False
    for settings in settings_list:
        user_min_conf = float(settings.min_confidence or 40)
        w_result = await db.execute(
            select(PaperWallet).where(PaperWallet.user_id == settings.user_id, PaperWallet.is_active == True)
        )
        wallet = w_result.scalars().first()
        if not wallet:
            continue

        for signal in active_signals:
            if float(signal.confidence or 0) < user_min_conf:
                continue
            h_result = await db.execute(
                select(PaperHolding).where(PaperHolding.wallet_id == wallet.id, PaperHolding.symbol == signal.symbol)
            )
            if h_result.scalars().first():
                continue
            trade_amount = min(float(settings.max_trade_amount), float(wallet.current_balance) * float(settings.max_portfolio_percentage) / 100)
            if trade_amount < 5:
                continue
            result = await execute_paper_trade(user_id=settings.user_id, wallet=wallet, symbol=signal.symbol, side="buy", amount_usdt=trade_amount, db=db, executed_by="paper_bot")
            if result.get("success"):
                # Set TP/SL from signal on the holding
                h_new = await db.execute(
                    select(PaperHolding).where(PaperHolding.wallet_id == wallet.id, PaperHolding.symbol == signal.symbol)
                )
                new_holding = h_new.scalars().first()
                if new_holding:
                    new_holding.take_profit_price = float(signal.target_1 or 0)
                    new_holding.stop_loss_price = float(signal.stop_loss or 0)
                    new_holding.signal_id = signal.id
                    new_holding.entry_trade_id = result.get("trade_id")
                logger.info(f"BUY {signal.symbol} @${result['price']:.2f} TP=${float(signal.target_1 or 0):.2f} SL=${float(signal.stop_loss or 0):.2f}")
                bought = True

    if bought:
        await db.commit()


async def _auto_sell_paper(db: AsyncSession, signal: TradeSignal, current_price: float):
    """Auto-sell paper holdings when signal closes."""
    from app.services.paper_trader import execute_paper_trade
    result = await db.execute(select(PaperBotSettings).where(PaperBotSettings.is_enabled == True))
    for settings in result.scalars().all():
        w_result = await db.execute(
            select(PaperWallet).where(PaperWallet.user_id == settings.user_id, PaperWallet.is_active == True)
        )
        wallet = w_result.scalars().first()
        if not wallet:
            continue
        h_result = await db.execute(
            select(PaperHolding).where(PaperHolding.wallet_id == wallet.id, PaperHolding.symbol == signal.symbol)
        )
        holding = h_result.scalars().first()
        if not holding or float(holding.quantity) <= 0:
            continue
        sell_amount = float(holding.quantity) * current_price
        if sell_amount > 0:
            await execute_paper_trade(user_id=settings.user_id, wallet=wallet, symbol=signal.symbol, side="sell", amount_usdt=sell_amount, db=db, executed_by="paper_bot")
            logger.info(f"SELL {signal.symbol} @${current_price:.2f} ({signal.status})")
