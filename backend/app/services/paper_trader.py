"""
Paper Trading Service — Executes virtual trades using real market prices.
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.paper_trading import PaperWallet, PaperHolding, PaperTrade, PaperBotSettings
from app.models.trade import BotSettings
from app.models.analysis import BotAnalysis
from app.services.binance_client import get_prices_batch

logger = logging.getLogger(__name__)


async def execute_paper_trade(
    user_id: str,
    wallet: PaperWallet,
    symbol: str,
    side: str,
    amount_usdt: float,
    db: AsyncSession,
    analysis_id: str = None,
    executed_by: str = "paper_bot",
) -> dict:
    """Execute a virtual trade using real market price."""
    try:
        # Get real price from Binance
        prices = await get_prices_batch([symbol])
        current_price = prices.get(symbol, 0)
        if current_price <= 0:
            return {"success": False, "error": f"لم يتم العثور على سعر {symbol}"}

        base_asset = symbol.replace("USDT", "").replace("BUSD", "")

        if side == "buy":
            if float(wallet.current_balance) < amount_usdt:
                return {"success": False, "error": f"رصيد غير كافٍ. المتاح: ${float(wallet.current_balance):.2f}"}

            quantity = amount_usdt / current_price
            wallet.current_balance = float(wallet.current_balance) - amount_usdt

            # Update holdings
            result = await db.execute(
                select(PaperHolding).where(
                    PaperHolding.wallet_id == wallet.id,
                    PaperHolding.symbol == symbol,
                )
            )
            holding = result.scalar_one_or_none()

            if holding:
                old_total = float(holding.quantity) * float(holding.avg_buy_price)
                new_total = old_total + amount_usdt
                holding.quantity = float(holding.quantity) + quantity
                holding.avg_buy_price = new_total / float(holding.quantity)
            else:
                holding = PaperHolding(
                    wallet_id=wallet.id,
                    symbol=symbol,
                    asset=base_asset,
                    quantity=quantity,
                    avg_buy_price=current_price,
                )
                db.add(holding)

            pnl = 0

        elif side == "sell":
            result = await db.execute(
                select(PaperHolding).where(
                    PaperHolding.wallet_id == wallet.id,
                    PaperHolding.symbol == symbol,
                )
            )
            holding = result.scalar_one_or_none()

            if not holding or float(holding.quantity) <= 0:
                return {"success": False, "error": f"لا تملك {base_asset} للبيع"}

            quantity = min(amount_usdt / current_price, float(holding.quantity))
            total_value = quantity * current_price
            pnl = (current_price - float(holding.avg_buy_price)) * quantity

            wallet.current_balance = float(wallet.current_balance) + total_value
            holding.quantity = float(holding.quantity) - quantity

            if float(holding.quantity) <= 0.00000001:
                await db.delete(holding)
        else:
            return {"success": False, "error": "نوع الصفقة غير صالح"}

        total_value = quantity * current_price

        trade = PaperTrade(
            wallet_id=wallet.id,
            user_id=user_id,
            analysis_id=analysis_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=current_price,
            total_value=total_value,
            pnl=pnl if side == "sell" else 0,
            status="filled",
            executed_by=executed_by,
        )
        db.add(trade)
        await db.flush()

        logger.info(f"Paper trade: {side.upper()} {symbol} qty={quantity:.6f} @ ${current_price:.2f}")

        return {
            "success": True,
            "trade_id": trade.id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": current_price,
            "total_value": total_value,
            "pnl": pnl,
            "balance": float(wallet.current_balance),
        }

    except Exception as e:
        logger.error(f"Paper trade failed: {e}")
        return {"success": False, "error": str(e)}


async def run_paper_bot_cycle(db: AsyncSession):
    """Run paper bot for all enabled users — auto-trade based on active signals."""
    from app.models.paper_trading import TradeSignal
    from app.models.trade import SupportedSymbol
    from app.services.signal_generator import generate_signals_live, update_signal_statuses

    result = await db.execute(
        select(PaperBotSettings).where(PaperBotSettings.is_enabled == True)
    )
    enabled_settings = result.scalars().all()

    if not enabled_settings:
        return

    # First: update signal statuses (close expired/hit targets)
    await update_signal_statuses(db)

    for settings in enabled_settings:
        # Get user's paper wallet
        w_result = await db.execute(
            select(PaperWallet).where(
                PaperWallet.user_id == settings.user_id,
                PaperWallet.is_active == True,
            )
        )
        wallet = w_result.scalar_one_or_none()
        if not wallet:
            continue

        # Check daily trade count
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        count_result = await db.execute(
            select(func.count(PaperTrade.id)).where(
                PaperTrade.user_id == settings.user_id,
                PaperTrade.executed_by == "paper_bot",
                PaperTrade.created_at >= today_start,
            )
        )
        today_trades = count_result.scalar() or 0
        if today_trades >= settings.max_trades_per_day:
            continue

        # Auto-sell holdings that hit target or stop — based on closed signals
        h_result = await db.execute(
            select(PaperHolding).where(PaperHolding.wallet_id == wallet.id)
        )
        holdings = h_result.scalars().all()
        for holding in holdings:
            if float(holding.quantity) <= 0:
                continue
            # Check if signal for this symbol was closed (hit_target/stopped/expired)
            sig_result = await db.execute(
                select(TradeSignal).where(
                    TradeSignal.symbol == holding.symbol,
                    TradeSignal.status.in_(["hit_target", "stopped", "expired"]),
                ).order_by(TradeSignal.closed_at.desc()).limit(1)
            )
            closed_signal = sig_result.scalar_one_or_none()
            if closed_signal and closed_signal.closed_at:
                # Check if closed recently (within last 10 minutes)
                closed_time = closed_signal.closed_at
                if hasattr(closed_time, 'tzinfo') and closed_time.tzinfo is None:
                    closed_time = closed_time.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - closed_time).total_seconds() < 600:
                    sell_amount = float(holding.quantity) * float(
                        (await get_prices_batch([holding.symbol])).get(holding.symbol, 0)
                    )
                    if sell_amount > 0:
                        await execute_paper_trade(
                            user_id=settings.user_id, wallet=wallet,
                            symbol=holding.symbol, side="sell",
                            amount_usdt=sell_amount, db=db,
                            executed_by="paper_bot",
                        )
                        logger.info(f"🤖 Auto-sell {holding.symbol} ({closed_signal.status})")

        # Auto-buy from active signals
        sig_result = await db.execute(
            select(TradeSignal).where(
                TradeSignal.status == "active",
                TradeSignal.signal_type == "long",
                TradeSignal.confidence >= float(settings.min_confidence or 85),
            )
        )
        active_signals = sig_result.scalars().all()

        for signal in active_signals:
            # Check if already holding this symbol
            existing = await db.execute(
                select(PaperHolding).where(
                    PaperHolding.wallet_id == wallet.id,
                    PaperHolding.symbol == signal.symbol,
                )
            )
            if existing.scalar_one_or_none():
                continue  # Already holding

            trade_amount = min(
                float(settings.max_trade_amount),
                float(wallet.current_balance) * float(settings.max_portfolio_percentage) / 100,
            )
            if trade_amount < 5:
                continue

            await execute_paper_trade(
                user_id=settings.user_id, wallet=wallet,
                symbol=signal.symbol, side="buy",
                amount_usdt=trade_amount, db=db,
                executed_by="paper_bot",
            )
            logger.info(f"🤖 Auto-buy {signal.symbol} (confidence: {signal.confidence}%)")

    await db.commit()
    logger.info("✅ Paper bot cycle complete")
