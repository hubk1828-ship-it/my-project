"""
Signal Generator — Produces trade signals with targets based on technical analysis + SMC.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.paper_trading import TradeSignal
from app.models.trade import SupportedSymbol
from app.services.analyzer import analyze_chart, check_momentum
from app.services.binance_client import get_prices_batch

logger = logging.getLogger(__name__)


def calculate_targets(price: float, side: str, support: float, resistance: float, atr_pct: float = 2.0) -> dict:
    """Calculate entry, targets, and stop loss based on S/R levels and price action."""
    if side == "long":
        stop_loss = max(support * 0.995, price * (1 - atr_pct * 1.5 / 100))
        target_1 = price * (1 + atr_pct / 100)
        target_2 = resistance
        target_3 = resistance * (1 + atr_pct / 100)
    else:  # short
        stop_loss = min(resistance * 1.005, price * (1 + atr_pct * 1.5 / 100))
        target_1 = price * (1 - atr_pct / 100)
        target_2 = support
        target_3 = support * (1 - atr_pct / 100)

    return {
        "entry_price": round(price, 8),
        "target_1": round(target_1, 8),
        "target_2": round(target_2, 8),
        "target_3": round(target_3, 8),
        "stop_loss": round(stop_loss, 8),
    }


async def generate_signals(db: AsyncSession) -> List[Dict]:
    """Generate trade signals for all active symbols."""
    result = await db.execute(
        select(SupportedSymbol).where(SupportedSymbol.is_active == True)
    )
    symbols = result.scalars().all()
    generated = []

    for sym in symbols:
        try:
            # Short-term analysis (1h)
            chart_1h = await analyze_chart(sym.symbol, "1h")
            momentum = await check_momentum(sym.symbol)

            # Long-term analysis (4h)
            chart_4h = await analyze_chart(sym.symbol, "4h")

            current_price = chart_1h.get("current_price", 0)
            if current_price <= 0:
                continue

            rsi = chart_1h.get("rsi", 50)
            support = chart_1h.get("support", 0)
            resistance = chart_1h.get("resistance", 0)
            smc_signal = chart_1h.get("smc_signal")
            trend_1h = chart_1h.get("trend", "عرضي")
            trend_4h = chart_4h.get("trend", "عرضي")

            # Skip if no clear direction
            if trend_1h == "عرضي" and (not smc_signal or smc_signal.get("confidence", 0) < 50):
                continue

            # Determine signal type
            signal_type = None
            confidence = 0
            reasons = []

            # SMC priority
            if smc_signal and smc_signal.get("confidence", 0) >= 60:
                smc_decision = smc_signal.get("decision")
                if smc_decision == "buy":
                    signal_type = "long"
                elif smc_decision == "sell":
                    signal_type = "short"
                confidence += smc_signal["confidence"] * 0.5
                reasons.extend(smc_signal.get("signals", []))

            # Classic TA
            if trend_1h == "صاعد" and rsi < 70:
                if signal_type != "short":
                    signal_type = signal_type or "long"
                    confidence += 25
                    reasons.append(f"📈 اتجاه صاعد على 1H (RSI: {rsi:.0f})")
            elif trend_1h == "هابط" and rsi > 30:
                if signal_type != "long":
                    signal_type = signal_type or "short"
                    confidence += 25
                    reasons.append(f"📉 اتجاه هابط على 1H (RSI: {rsi:.0f})")

            # 4H confirmation
            if trend_4h == "صاعد" and signal_type == "long":
                confidence += 15
                reasons.append("✅ تأكيد صاعد على 4H")
            elif trend_4h == "هابط" and signal_type == "short":
                confidence += 15
                reasons.append("✅ تأكيد هابط على 4H")
            elif trend_4h != trend_1h:
                confidence -= 10
                reasons.append(f"⚠️ تضارب بين 1H ({trend_1h}) و 4H ({trend_4h})")

            # Momentum
            if momentum.get("is_real"):
                confidence += 10
                reasons.append(f"✅ زخم حقيقي ({momentum['reason']})")

            if not signal_type or confidence < 40:
                continue

            confidence = min(confidence, 100)

            # Calculate targets
            atr_pct = abs(resistance - support) / current_price * 100 if resistance > support else 2.0
            atr_pct = max(1.0, min(atr_pct, 8.0))
            targets = calculate_targets(current_price, signal_type, support, resistance, atr_pct)

            # Check for duplicate active signal
            existing = await db.execute(
                select(TradeSignal).where(
                    TradeSignal.symbol == sym.symbol,
                    TradeSignal.status == "active",
                    TradeSignal.signal_type == signal_type,
                )
            )
            if existing.scalar_one_or_none():
                continue

            # SHORT-TERM signal (1h-based)
            short_signal = TradeSignal(
                symbol=sym.symbol,
                signal_type=signal_type,
                timeframe_type="short_term",
                entry_price=targets["entry_price"],
                target_1=targets["target_1"],
                target_2=targets["target_2"],
                target_3=targets["target_3"],
                stop_loss=targets["stop_loss"],
                confidence=confidence,
                reasoning="\n".join(reasons),
                status="active",
                technical_data={
                    "rsi_1h": chart_1h.get("rsi"),
                    "ema20_1h": chart_1h.get("ema20"),
                    "ema50_1h": chart_1h.get("ema50"),
                    "trend_1h": trend_1h,
                    "trend_4h": trend_4h,
                    "volume_ratio": momentum.get("ratio"),
                    "support": support,
                    "resistance": resistance,
                },
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            )
            db.add(short_signal)
            generated.append({"symbol": sym.symbol, "type": signal_type, "tf": "short_term", "confidence": confidence})

            # LONG-TERM signal (4h-based, only if 4h confirms)
            if trend_4h in ("صاعد", "هابط"):
                lt_signal_type = "long" if trend_4h == "صاعد" else "short"
                support_4h = chart_4h.get("support", 0)
                resistance_4h = chart_4h.get("resistance", 0)
                atr_4h = abs(resistance_4h - support_4h) / current_price * 100 if resistance_4h > support_4h else 3.0
                atr_4h = max(2.0, min(atr_4h, 12.0))
                lt_targets = calculate_targets(current_price, lt_signal_type, support_4h, resistance_4h, atr_4h)

                lt_reasons = [
                    f"📊 تحليل طويل المدى على 4H — اتجاه {trend_4h}",
                    f"RSI 4H: {chart_4h.get('rsi', 0):.0f}",
                ]
                if smc_signal:
                    lt_reasons.extend(smc_signal.get("signals", []))

                existing_lt = await db.execute(
                    select(TradeSignal).where(
                        TradeSignal.symbol == sym.symbol,
                        TradeSignal.status == "active",
                        TradeSignal.timeframe_type == "long_term",
                    )
                )
                if not existing_lt.scalar_one_or_none():
                    lt_signal = TradeSignal(
                        symbol=sym.symbol,
                        signal_type=lt_signal_type,
                        timeframe_type="long_term",
                        entry_price=lt_targets["entry_price"],
                        target_1=lt_targets["target_1"],
                        target_2=lt_targets["target_2"],
                        target_3=lt_targets["target_3"],
                        stop_loss=lt_targets["stop_loss"],
                        confidence=min(confidence + 5, 100),
                        reasoning="\n".join(lt_reasons),
                        status="active",
                        technical_data={
                            "rsi_4h": chart_4h.get("rsi"),
                            "ema20_4h": chart_4h.get("ema20"),
                            "ema50_4h": chart_4h.get("ema50"),
                            "trend_4h": trend_4h,
                            "support_4h": support_4h,
                            "resistance_4h": resistance_4h,
                        },
                        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                    )
                    db.add(lt_signal)
                    generated.append({"symbol": sym.symbol, "type": lt_signal_type, "tf": "long_term"})

        except Exception as e:
            logger.error(f"Signal generation failed for {sym.symbol}: {e}")

    await db.commit()
    logger.info(f"✅ Generated {len(generated)} trade signals")
    return generated


async def update_signal_statuses(db: AsyncSession):
    """Check active signals and update their status based on current prices."""
    result = await db.execute(
        select(TradeSignal).where(TradeSignal.status == "active")
    )
    signals = result.scalars().all()

    if not signals:
        return

    # Get all unique symbols
    symbols = list(set(s.symbol for s in signals))
    prices = await get_prices_batch(symbols)

    now = datetime.now(timezone.utc)

    for signal in signals:
        price = prices.get(signal.symbol, 0)
        if price <= 0:
            continue

        # Check expiry
        if signal.expires_at and now > signal.expires_at:
            signal.status = "expired"
            signal.closed_at = now
            continue

        # Check stop loss
        if signal.signal_type == "long" and price <= float(signal.stop_loss):
            signal.status = "stopped"
            signal.closed_at = now
            continue
        elif signal.signal_type == "short" and price >= float(signal.stop_loss):
            signal.status = "stopped"
            signal.closed_at = now
            continue

        # Check targets hit
        if signal.signal_type == "long":
            if signal.target_3 and price >= float(signal.target_3):
                signal.status = "hit_target"
                signal.hit_target_level = 3
                signal.closed_at = now
            elif signal.target_2 and price >= float(signal.target_2):
                signal.hit_target_level = 2
            elif price >= float(signal.target_1):
                signal.hit_target_level = 1
        else:  # short
            if signal.target_3 and price <= float(signal.target_3):
                signal.status = "hit_target"
                signal.hit_target_level = 3
                signal.closed_at = now
            elif signal.target_2 and price <= float(signal.target_2):
                signal.hit_target_level = 2
            elif price <= float(signal.target_1):
                signal.hit_target_level = 1

    await db.commit()
    logger.info("✅ Signal statuses updated")
