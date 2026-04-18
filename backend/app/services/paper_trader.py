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
    """Run paper bot for all users who have it enabled — uses same analysis as real bot."""
    from app.models.trade import SupportedSymbol

    result = await db.execute(
        select(PaperBotSettings).where(PaperBotSettings.is_enabled == True)
    )
    enabled_settings = result.scalars().all()

    if not enabled_settings:
        return

    # Get active symbols
    sym_result = await db.execute(
        select(SupportedSymbol).where(SupportedSymbol.is_active == True)
    )
    symbols = sym_result.scalars().all()

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

        for sym in symbols:
            # Get latest analysis
            a_result = await db.execute(
                select(BotAnalysis)
                .where(BotAnalysis.symbol == sym.symbol)
                .order_by(BotAnalysis.created_at.desc())
                .limit(1)
            )
            analysis = a_result.scalar_one_or_none()
            if not analysis or analysis.decision == "no_opportunity":
                continue

            trade_amount = min(
                float(settings.max_trade_amount),
                float(wallet.current_balance) * float(settings.max_portfolio_percentage) / 100,
            )
            if trade_amount < 5:
                continue

            await execute_paper_trade(
                user_id=settings.user_id,
                wallet=wallet,
                symbol=sym.symbol,
                side=analysis.decision,
                amount_usdt=trade_amount,
                db=db,
                analysis_id=analysis.id,
                executed_by="paper_bot",
            )

    await db.commit()
    logger.info("✅ Paper bot cycle complete")
