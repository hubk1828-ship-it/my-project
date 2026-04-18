"""
Signal Generator — Produces trade signals with targets based on existing analysis results.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.paper_trading import TradeSignal
from app.models.trade import SupportedSymbol
from app.models.analysis import BotAnalysis
from app.services.binance_client import get_prices_batch

logger = logging.getLogger(__name__)


def calculate_targets(price: float, side: str, support: float, resistance: float, atr_pct: float = 2.0) -> dict:
    """Calculate entry, targets, and stop loss."""
    if side == "long":
        stop_loss = max(support * 0.995, price * (1 - atr_pct * 1.5 / 100))
        target_1 = price * (1 + atr_pct / 100)
        target_2 = resistance if resistance > price * 1.005 else price * (1 + atr_pct * 1.8 / 100)
        target_3 = resistance * (1 + atr_pct / 100) if resistance > price else price * (1 + atr_pct * 2.5 / 100)
    else:  # short
        stop_loss = min(resistance * 1.005, price * (1 + atr_pct * 1.5 / 100))
        target_1 = price * (1 - atr_pct / 100)
        target_2 = support if support < price * 0.995 else price * (1 - atr_pct * 1.8 / 100)
        target_3 = support * (1 - atr_pct / 100) if support < price else price * (1 - atr_pct * 2.5 / 100)

    return {
        "entry_price": round(price, 8),
        "target_1": round(target_1, 8),
        "target_2": round(target_2, 8),
        "target_3": round(target_3, 8),
        "stop_loss": round(stop_loss, 8),
    }


async def generate_signals(db: AsyncSession) -> List[Dict]:
    """Generate trade signals from existing bot analysis results."""
    # Get latest analysis for each symbol (from the last 6 hours)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)

    result = await db.execute(
        select(SupportedSymbol).where(SupportedSymbol.is_active == True)
    )
    symbols = result.scalars().all()
    generated = []

    for sym in symbols:
        try:
            # Get the most recent analysis for this symbol
            a_result = await db.execute(
                select(BotAnalysis)
                .where(
                    BotAnalysis.symbol == sym.symbol,
                    BotAnalysis.created_at >= cutoff,
                )
                .order_by(BotAnalysis.created_at.desc())
                .limit(1)
            )
            analysis = a_result.scalar_one_or_none()
            if not analysis:
                continue

            # Skip no_opportunity
            if analysis.decision == "no_opportunity":
                continue

            # Extract data from existing analysis
            indicators = analysis.technical_indicators or {}
            current_price = indicators.get("current_price", 0)
            if current_price <= 0:
                continue

            support = indicators.get("support", current_price * 0.97)
            resistance = indicators.get("resistance", current_price * 1.03)
            rsi = indicators.get("rsi", 50)
            trend = indicators.get("trend", "عرضي")
            volume_ratio = indicators.get("volume_ratio", 0)
            smc = indicators.get("smc")
            confidence = float(analysis.confidence_score or 50)

            # Determine signal type from analysis decision
            signal_type = "long" if analysis.decision == "buy" else "short"

            # Build reasoning from analysis
            reasons = analysis.reasoning.split("\n") if analysis.reasoning else []

            # Check for duplicate active signal for same symbol + type
            existing = await db.execute(
                select(TradeSignal).where(
                    TradeSignal.symbol == sym.symbol,
                    TradeSignal.status == "active",
                    TradeSignal.signal_type == signal_type,
                )
            )
            if existing.scalar_one_or_none():
                continue

            # Calculate ATR-like percentage from support/resistance
            atr_pct = abs(resistance - support) / current_price * 100 if resistance > support else 2.0
            atr_pct = max(1.0, min(atr_pct, 8.0))

            # Calculate targets
            targets = calculate_targets(current_price, signal_type, support, resistance, atr_pct)

            # SHORT-TERM signal
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
                reasoning=analysis.reasoning or "بناءً على التحليل الفني",
                status="active",
                technical_data={
                    "rsi": rsi,
                    "trend": trend,
                    "volume_ratio": volume_ratio,
                    "support": support,
                    "resistance": resistance,
                    "analysis_decision": analysis.decision,
                    "analysis_id": analysis.id,
                },
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            )
            db.add(short_signal)
            generated.append({"symbol": sym.symbol, "type": signal_type, "tf": "short_term", "confidence": confidence})

            # LONG-TERM signal (only if confidence is high enough)
            if confidence >= 50:
                # Check for duplicate long-term
                existing_lt = await db.execute(
                    select(TradeSignal).where(
                        TradeSignal.symbol == sym.symbol,
                        TradeSignal.status == "active",
                        TradeSignal.timeframe_type == "long_term",
                    )
                )
                if not existing_lt.scalar_one_or_none():
                    lt_atr = atr_pct * 1.5
                    lt_targets = calculate_targets(current_price, signal_type, support, resistance, lt_atr)

                    lt_signal = TradeSignal(
                        symbol=sym.symbol,
                        signal_type=signal_type,
                        timeframe_type="long_term",
                        entry_price=lt_targets["entry_price"],
                        target_1=lt_targets["target_1"],
                        target_2=lt_targets["target_2"],
                        target_3=lt_targets["target_3"],
                        stop_loss=lt_targets["stop_loss"],
                        confidence=min(confidence + 5, 100),
                        reasoning=f"📊 توصية طويلة المدى\n{analysis.reasoning or ''}",
                        status="active",
                        technical_data={
                            "rsi": rsi,
                            "trend": trend,
                            "support": support,
                            "resistance": resistance,
                        },
                        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                    )
                    db.add(lt_signal)
                    generated.append({"symbol": sym.symbol, "type": signal_type, "tf": "long_term"})

        except Exception as e:
            logger.error(f"Signal generation failed for {sym.symbol}: {e}")

    await db.commit()
    logger.info(f"✅ Generated {len(generated)} trade signals")
    return generated


async def generate_signals_live(db: AsyncSession, timeframe: str = "1h") -> List[Dict]:
    """Generate signals by running live analysis with a specific timeframe."""
    from app.services.analyzer import analyze_chart, check_momentum

    result = await db.execute(
        select(SupportedSymbol).where(SupportedSymbol.is_active == True)
    )
    symbols = result.scalars().all()
    generated = []

    for sym in symbols:
        try:
            chart = await analyze_chart(sym.symbol, timeframe)
            momentum = await check_momentum(sym.symbol)

            current_price = chart.get("current_price", 0)
            if current_price <= 0:
                continue

            rsi = chart.get("rsi", 50)
            support = chart.get("support", current_price * 0.97)
            resistance = chart.get("resistance", current_price * 1.03)
            trend = chart.get("trend", "عرضي")
            smc_signal = chart.get("smc_signal")
            smc_data = chart.get("smc")

            # Determine signal from analysis
            signal_type = None
            confidence = 0
            reasons = []

            # SMC signal
            if smc_signal and smc_signal.get("confidence", 0) >= 40:
                smc_decision = smc_signal.get("decision")
                if smc_decision in ("buy", "sell"):
                    signal_type = "long" if smc_decision == "buy" else "short"
                    confidence += smc_signal["confidence"] * 0.5
                    reasons.extend(smc_signal.get("signals", []))

            # Trend-based
            if trend == "صاعد" and rsi < 75:
                signal_type = signal_type or "long"
                confidence += 25
                reasons.append(f"📈 اتجاه صاعد على {timeframe} (RSI: {rsi:.0f})")
            elif trend == "هابط" and rsi > 25:
                signal_type = signal_type or "short"
                confidence += 25
                reasons.append(f"📉 اتجاه هابط على {timeframe} (RSI: {rsi:.0f})")

            # Momentum
            if momentum.get("is_real"):
                confidence += 10
                reasons.append(f"✅ زخم حقيقي ({momentum['reason']})")

            if not signal_type:
                continue

            confidence = min(max(confidence, 30), 100)

            # Check duplicate
            existing = await db.execute(
                select(TradeSignal).where(
                    TradeSignal.symbol == sym.symbol,
                    TradeSignal.status == "active",
                    TradeSignal.signal_type == signal_type,
                )
            )
            if existing.scalar_one_or_none():
                continue

            atr_pct = abs(resistance - support) / current_price * 100 if resistance > support else 2.0
            atr_pct = max(1.0, min(atr_pct, 8.0))
            targets = calculate_targets(current_price, signal_type, support, resistance, atr_pct)

            # Determine timeframe type
            short_tfs = ["1m", "5m", "15m", "30m", "1h", "2h"]
            tf_type = "short_term" if timeframe in short_tfs else "long_term"
            expiry = timedelta(hours=24) if tf_type == "short_term" else timedelta(days=7)

            signal = TradeSignal(
                symbol=sym.symbol,
                signal_type=signal_type,
                timeframe_type=tf_type,
                entry_price=targets["entry_price"],
                target_1=targets["target_1"],
                target_2=targets["target_2"],
                target_3=targets["target_3"],
                stop_loss=targets["stop_loss"],
                confidence=confidence,
                reasoning="\n".join(reasons),
                status="active",
                technical_data={
                    "timeframe": timeframe,
                    "rsi": rsi,
                    "trend": trend,
                    "support": support,
                    "resistance": resistance,
                    "volume_ratio": momentum.get("ratio"),
                },
                expires_at=datetime.now(timezone.utc) + expiry,
            )
            db.add(signal)
            generated.append({"symbol": sym.symbol, "type": signal_type, "tf": tf_type, "confidence": confidence, "timeframe": timeframe})

        except Exception as e:
            logger.error(f"Live signal generation failed for {sym.symbol}: {e}")

    await db.commit()
    logger.info(f"✅ Generated {len(generated)} live signals ({timeframe})")
    return generated


async def update_signal_statuses(db: AsyncSession):
    """Check active signals and update their status based on current prices."""
    result = await db.execute(
        select(TradeSignal).where(TradeSignal.status == "active")
    )
    signals = result.scalars().all()

    if not signals:
        return

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
