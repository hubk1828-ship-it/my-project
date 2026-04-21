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
        # === Risk Checks ===
        from app.services.risk_manager import check_cooldown, check_drawdown

        # Cooldown: no same-symbol trade within 5 minutes
        cd = await check_cooldown(str(wallet.id), symbol, db, cooldown_minutes=5)
        if not cd["can_trade"]:
            return {"success": False, "error": f"⏳ {cd['reason']}"}

        # Drawdown protection (5%)
        dd = await check_drawdown(wallet, db, max_drawdown_pct=5.0)
        if not dd["safe"]:
            return {"success": False, "error": f"🛑 Drawdown {dd['drawdown_pct']}% — إيقاف التداول"}

        # Get real price
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

            # Always create a new independent holding (each signal = separate position)
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
                    PaperHolding.quantity > 0,
                ).order_by(PaperHolding.updated_at.asc()).limit(1)
            )
            holding = result.scalars().first()

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
    """Run paper bot — target-based trading. Sells only on TP/SL hit."""
    from app.models.paper_trading import TradeSignal
    from app.services.binance_client import _price_cache

    result = await db.execute(
        select(PaperBotSettings).where(PaperBotSettings.is_enabled == True)
    )
    enabled_settings = result.scalars().all()

    if not enabled_settings:
        return

    for settings in enabled_settings:
        cycle_log = []

        # Get wallet
        w_result = await db.execute(
            select(PaperWallet).where(
                PaperWallet.user_id == settings.user_id,
                PaperWallet.is_active == True,
            )
        )
        wallet = w_result.scalars().first()
        if not wallet:
            continue

        # ═══════════════════════════════════════
        # 1️⃣ CHECK OPEN POSITIONS — TP/SL EXIT
        # ═══════════════════════════════════════
        h_result = await db.execute(
            select(PaperHolding).where(PaperHolding.wallet_id == wallet.id)
        )
        holdings = h_result.scalars().all()
        sell_count = 0

        for holding in holdings:
            qty = float(holding.quantity)
            if qty <= 0:
                continue

            # Get current price from WebSocket cache
            import time as _time
            cached = _price_cache.get(holding.symbol)
            if not cached:
                prices = await get_prices_batch([holding.symbol])
                current_price = prices.get(holding.symbol, 0)
            else:
                price_val, ts = cached
                current_price = price_val if (_time.time() - ts) < 60 else 0

            if current_price <= 0:
                continue

            tp = float(holding.take_profit_price or 0)
            sl = float(holding.stop_loss_price or 0)
            entry = float(holding.avg_buy_price)
            sell_reason = None

            # Check TP/SL
            if tp > 0 and current_price >= tp:
                sell_reason = "take_profit"
            elif sl > 0 and current_price <= sl:
                sell_reason = "stop_loss"

            if sell_reason:
                sell_amount = qty * current_price
                pnl = (current_price - entry) * qty
                result = await execute_paper_trade(
                    user_id=settings.user_id, wallet=wallet,
                    symbol=holding.symbol, side="sell",
                    amount_usdt=sell_amount, db=db,
                    executed_by="paper_bot",
                )
                if result.get("success"):
                    sell_count += 1
                    emoji = "✅" if sell_reason == "take_profit" else "🛑"
                    logger.info(
                        f"{emoji} {holding.symbol} {sell_reason} | "
                        f"entry=${entry:.2f} exit=${current_price:.2f} PnL=${pnl:+.2f}"
                    )

        if sell_count > 0:
            cycle_log.append(f"💰 {sell_count} sold (TP/SL)")

        # ═══════════════════════════════════════
        # 2️⃣ FIND NEW OPPORTUNITIES — BUY
        # ═══════════════════════════════════════

        # Count open positions
        open_result = await db.execute(
            select(func.count(PaperHolding.id)).where(
                PaperHolding.wallet_id == wallet.id,
                PaperHolding.quantity > 0,
            )
        )
        open_positions = open_result.scalar() or 0
        max_positions = int(getattr(settings, 'max_open_positions', 5) or 5)

        if open_positions >= max_positions:
            cycle_log.append(f"⛔ max positions ({open_positions}/{max_positions})")
        else:
            # Get active signals
            user_min_conf = float(settings.min_confidence or 40)
            sig_result = await db.execute(
                select(TradeSignal).where(
                    TradeSignal.status == "active",
                    TradeSignal.signal_type.in_(["long", "short"]),
                    TradeSignal.confidence >= min(user_min_conf, 70),
                )
            )
            active_signals = sig_result.scalars().all()

            buy_count = 0
            for signal in active_signals:
                if open_positions + buy_count >= max_positions:
                    break

                # Already bought this exact signal?
                existing = await db.execute(
                    select(PaperHolding).where(
                        PaperHolding.wallet_id == wallet.id,
                        PaperHolding.signal_id == signal.id,
                        PaperHolding.quantity > 0,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                # Check daily limit PER TRADE
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
                    cycle_log.append(f"⛔ daily limit {today_trades}/{settings.max_trades_per_day}")
                    break

                # Calculate trade amount
                trade_size = float(getattr(settings, 'trade_size_pct', 20) or 20)
                trade_amount = min(
                    float(wallet.current_balance) * trade_size / 100,
                    float(settings.max_trade_amount),
                    float(wallet.current_balance) * 0.95,
                )
                if trade_amount < 5:
                    continue

                # Execute buy
                result = await execute_paper_trade(
                    user_id=settings.user_id, wallet=wallet,
                    symbol=signal.symbol, side="buy",
                    amount_usdt=trade_amount, db=db,
                    executed_by="paper_bot",
                )
                if result.get("success"):
                    # Set TP/SL — find the newest holding (no signal_id yet)
                    h_res = await db.execute(
                        select(PaperHolding).where(
                            PaperHolding.wallet_id == wallet.id,
                            PaperHolding.symbol == signal.symbol,
                            PaperHolding.signal_id == None,
                        ).order_by(PaperHolding.updated_at.desc()).limit(1)
                    )
                    new_holding = h_res.scalar_one_or_none()
                    if new_holding:
                        new_holding.take_profit_price = float(signal.target_1 or 0)
                        new_holding.stop_loss_price = float(signal.stop_loss or 0)
                        new_holding.signal_id = signal.id
                        new_holding.entry_trade_id = result.get("trade_id")

                    buy_count += 1
                    logger.info(
                        f"🤖 BUY {signal.symbol} ${trade_amount:.0f} | "
                        f"TP=${float(signal.target_1 or 0):.2f} SL=${float(signal.stop_loss or 0):.2f} "
                        f"conf={signal.confidence}%"
                    )

            if buy_count > 0:
                cycle_log.append(f"✅ {buy_count} bought")
            if buy_count == 0 and sell_count == 0:
                cycle_log.append("➖ no trades")

        if cycle_log:
            logger.info(f"🤖 bot [{settings.user_id[:8]}]: {' | '.join(cycle_log)}")

    await db.commit()
