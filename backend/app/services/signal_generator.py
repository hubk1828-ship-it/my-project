"""
Signal Generator — Smart signals with calculated durations and conservative targets.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.paper_trading import TradeSignal
from app.models.trade import SupportedSymbol
from app.models.analysis import BotAnalysis
from app.services.binance_client import get_prices_batch

logger = logging.getLogger(__name__)


def calculate_targets(price: float, side: str, support: float, resistance: float, atr_pct: float = 2.0) -> dict:
    """Calculate CONSERVATIVE targets — closer targets for higher success rate."""
    # Use tighter targets: 40%, 70%, 100% of ATR instead of 100%, 180%, 250%
    if side == "long":
        stop_loss = max(support * 0.998, price * (1 - atr_pct * 0.8 / 100))
        target_1 = price * (1 + atr_pct * 0.4 / 100)
        target_2 = price * (1 + atr_pct * 0.7 / 100)
        target_3 = min(resistance, price * (1 + atr_pct / 100))
    else:
        stop_loss = min(resistance * 1.002, price * (1 + atr_pct * 0.8 / 100))
        target_1 = price * (1 - atr_pct * 0.4 / 100)
        target_2 = price * (1 - atr_pct * 0.7 / 100)
        target_3 = max(support, price * (1 - atr_pct / 100))

    return {
        "entry_price": round(price, 8),
        "target_1": round(target_1, 8),
        "target_2": round(target_2, 8),
        "target_3": round(target_3, 8),
        "stop_loss": round(stop_loss, 8),
    }


def estimate_signal_duration(timeframe: str, volatility_pct: float, volume_ratio: float) -> dict:
    """
    Signal duration = matches the selected timeframe exactly.
    Short-term frames get exact timeframe duration (max 1 hour).
    """
    # Duration matches the timeframe exactly (in minutes)
    tf_minutes = {
        "1m": 1, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "2h": 120, "4h": 240,
        "6h": 360, "8h": 480, "12h": 720,
        "1d": 1440, "3d": 4320, "1w": 10080, "1M": 43200,
    }
    minutes = tf_minutes.get(timeframe, 60)
    short_tfs = ["1m", "5m", "15m", "30m", "1h"]
    is_short = timeframe in short_tfs

    # Cap short-term to max 60 minutes
    if is_short and minutes > 60:
        minutes = 60

    hours = max(0.02, minutes / 60)  # min ~1 minute
    return {
        "duration_hours": round(hours, 2),
        "duration_minutes": minutes,
        "expires_at": datetime.utcnow() + timedelta(minutes=minutes),
        "reason": f"مدة {minutes} دقيقة (فريم {timeframe})",
        "is_short_term": is_short,
    }


async def generate_signals(db: AsyncSession) -> List[Dict]:
    """Generate signals from existing analysis results (Gemini-based)."""
    result = await db.execute(
        select(SupportedSymbol).where(SupportedSymbol.is_active == True)
    )
    symbols = result.scalars().all()
    generated = []

    for sym in symbols:
        try:
            a_result = await db.execute(
                select(BotAnalysis)
                .where(BotAnalysis.symbol == sym.symbol)
                .order_by(BotAnalysis.created_at.desc())
                .limit(1)
            )
            analysis = a_result.scalar_one_or_none()
            if not analysis or analysis.decision == "no_opportunity":
                continue

            # Skip Gemini failures
            indicators = analysis.technical_indicators or {}
            if indicators.get("gemini_status") == "failed":
                continue

            current_price = indicators.get("current_price", 0)
            if current_price <= 0:
                continue

            confidence = float(analysis.confidence_score or 0)
            signal_type = "long" if analysis.decision == "buy" else "short"

            # Check for existing active signal
            existing = await db.execute(
                select(TradeSignal).where(
                    TradeSignal.symbol == sym.symbol,
                    TradeSignal.status == "active",
                )
            )
            if existing.scalars().first():
                continue

            # Use AI-provided targets if available (from Confluence analyzer)
            ai_entry = indicators.get("entry_price")
            ai_tp1 = indicators.get("tp1")
            ai_sl = indicators.get("stop_loss")

            if ai_entry and ai_tp1 and ai_sl:
                targets = {
                    "entry_price": float(ai_entry),
                    "target_1": float(ai_tp1),
                    "target_2": float(indicators.get("tp2", ai_tp1)),
                    "target_3": float(indicators.get("tp3", ai_tp1)),
                    "stop_loss": float(ai_sl),
                }
                duration_minutes = indicators.get("duration_minutes", 60)
                timeframe_used = indicators.get("timeframe", "1h")
            else:
                support = indicators.get("support", current_price * 0.97)
                resistance = indicators.get("resistance", current_price * 1.03)
                atr_pct = abs(resistance - support) / current_price * 100 if resistance > support else 2.0
                atr_pct = max(1.0, min(atr_pct, 8.0))
                targets = calculate_targets(current_price, signal_type, support, resistance, atr_pct)
                duration_minutes = 60
                timeframe_used = "1h"

            volume_ratio = indicators.get("volume_ratio", 1)
            duration = estimate_signal_duration(timeframe_used, 2.0, volume_ratio if volume_ratio else 1)

            signal = TradeSignal(
                symbol=sym.symbol,
                signal_type=signal_type,
                timeframe_type="short_term",
                entry_price=targets["entry_price"],
                target_1=targets["target_1"],
                target_2=targets["target_2"],
                target_3=targets["target_3"],
                stop_loss=targets["stop_loss"],
                confidence=confidence,
                reasoning=analysis.reasoning or "بناءً على تحليل Gemini AI",
                status="active",
                technical_data={
                    **indicators,
                    "analysis_id": analysis.id,
                    "duration_reason": duration["reason"],
                    "source": "gemini_confluence",
                },
                expires_at=duration["expires_at"],
            )
            db.add(signal)
            generated.append({"symbol": sym.symbol, "type": signal_type, "tf": "short_term", "confidence": confidence})

        except Exception as e:
            logger.error(f"Signal generation failed for {sym.symbol}: {e}")

    await db.commit()
    logger.info(f"✅ Generated {len(generated)} trade signals")
    return generated


async def generate_signals_live(db: AsyncSession, timeframe: str = "1h") -> List[Dict]:
    """Generate signals using Gemini AI Confluence analysis."""
    from app.services.confluence_analyzer import analyze_symbol_confluence

    result = await db.execute(
        select(SupportedSymbol).where(SupportedSymbol.is_active == True)
    )
    symbols = result.scalars().all()
    generated = []

    for sym in symbols:
        try:
            # Use Gemini Confluence analyzer
            analysis_result = await analyze_symbol_confluence(sym.symbol, sym.base_asset)

            decision = analysis_result.get("decision", "no_opportunity")
            if decision == "no_opportunity":
                continue

            indicators = analysis_result.get("technical_indicators", {})
            
            # Skip Gemini failures
            if indicators.get("gemini_status") == "failed":
                logger.warning(f"⚠️ Skipping {sym.symbol} — Gemini failed")
                continue

            confidence = float(analysis_result.get("confidence_score", 0))
            signal_type = "long" if decision == "buy" else "short"
            current_price = indicators.get("current_price", 0)
            if current_price <= 0:
                continue

            # Duplicate check — no active signal for same symbol
            existing = await db.execute(
                select(TradeSignal).where(
                    TradeSignal.symbol == sym.symbol,
                    TradeSignal.status == "active",
                )
            )
            if existing.scalar_one_or_none():
                continue

            # Use Gemini-provided targets if available
            ai_entry = indicators.get("entry_price")
            ai_tp1 = indicators.get("tp1")
            ai_sl = indicators.get("stop_loss")

            if ai_entry and ai_tp1 and ai_sl:
                targets = {
                    "entry_price": float(ai_entry),
                    "target_1": float(ai_tp1),
                    "target_2": float(indicators.get("tp2", ai_tp1)),
                    "target_3": float(indicators.get("tp3", ai_tp1)),
                    "stop_loss": float(ai_sl),
                }
            else:
                support = indicators.get("support", current_price * 0.97)
                resistance = indicators.get("resistance", current_price * 1.03)
                atr_pct = abs(resistance - support) / current_price * 100 if resistance > support else 2.0
                atr_pct = max(1.0, min(atr_pct, 8.0))
                targets = calculate_targets(current_price, signal_type, support, resistance, atr_pct)

            timeframe_used = indicators.get("timeframe", timeframe)
            volume_ratio = indicators.get("volume_ratio", 1)
            duration = estimate_signal_duration(timeframe_used, 2.0, volume_ratio if volume_ratio else 1)
            tf_type = "short_term" if duration["is_short_term"] else "long_term"

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
                reasoning=analysis_result.get("reasoning", "بناءً على تحليل Gemini AI"),
                status="active",
                technical_data={
                    **indicators,
                    "timeframe": timeframe_used,
                    "duration_minutes": duration["duration_minutes"],
                    "duration_reason": duration["reason"],
                    "source": "gemini_confluence",
                },
                expires_at=duration["expires_at"],
            )
            db.add(signal)
            generated.append({
                "symbol": sym.symbol, "type": signal_type, "tf": tf_type,
                "confidence": confidence, "timeframe": timeframe_used,
                "duration_minutes": duration["duration_minutes"],
            })

        except Exception as e:
            logger.error(f"Live signal generation failed for {sym.symbol}: {e}")

    await db.commit()
    logger.info(f"✅ Generated {len(generated)} live signals (Gemini)")
    return generated


async def update_signal_statuses(db: AsyncSession):
    """Check active signals — auto-close expired ones and calculate PnL."""
    result = await db.execute(
        select(TradeSignal).where(TradeSignal.status == "active")
    )
    signals = result.scalars().all()
    if not signals:
        return

    symbols = list(set(s.symbol for s in signals))
    prices = await get_prices_batch(symbols)
    now = datetime.utcnow()

    for signal in signals:
        price = prices.get(signal.symbol, 0)
        if price <= 0:
            continue

        # Check expiry (timezone-safe)
        expires = signal.expires_at
        if expires:
            if hasattr(expires, 'tzinfo') and expires.tzinfo:
                expires = expires.replace(tzinfo=None)
            if now > expires:
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
        else:
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


async def get_signal_performance(db: AsyncSession, symbol: str = None) -> dict:
    """Analyze signal performance — success/failure rates."""
    query = select(TradeSignal).where(TradeSignal.status.in_(["hit_target", "stopped", "expired"]))
    if symbol:
        query = query.where(TradeSignal.symbol == symbol)

    result = await db.execute(query)
    closed_signals = result.scalars().all()

    if not closed_signals:
        return {"total": 0, "success_rate": 0, "loss_rate": 0, "signals": []}

    hits = [s for s in closed_signals if s.status == "hit_target"]
    stops = [s for s in closed_signals if s.status == "stopped"]
    expired = [s for s in closed_signals if s.status == "expired"]
    total = len(closed_signals)

    # Calculate PnL for each
    performance_list = []
    total_pnl_pct = 0
    for s in closed_signals:
        entry = float(s.entry_price)
        if s.status == "hit_target" and s.hit_target_level:
            target_key = f"target_{s.hit_target_level}"
            target_val = float(getattr(s, target_key, entry))
            pnl_pct = abs(target_val - entry) / entry * 100
        elif s.status == "stopped":
            pnl_pct = -abs(float(s.stop_loss) - entry) / entry * 100
        else:
            pnl_pct = 0

        total_pnl_pct += pnl_pct
        performance_list.append({
            "id": s.id,
            "symbol": s.symbol,
            "signal_type": s.signal_type,
            "status": s.status,
            "confidence": float(s.confidence),
            "pnl_pct": round(pnl_pct, 2),
            "entry_price": entry,
            "hit_level": s.hit_target_level,
            "created_at": str(s.created_at) if s.created_at else None,
            "closed_at": str(s.closed_at) if s.closed_at else None,
        })

    return {
        "total": total,
        "success": len(hits),
        "stopped": len(stops),
        "expired": len(expired),
        "success_rate": round(len(hits) / total * 100, 1) if total else 0,
        "loss_rate": round(len(stops) / total * 100, 1) if total else 0,
        "avg_pnl_pct": round(total_pnl_pct / total, 2) if total else 0,
        "total_pnl_pct": round(total_pnl_pct, 2),
        "signals": sorted(performance_list, key=lambda x: x.get("created_at", ""), reverse=True),
    }


async def analyze_bot_losses(db: AsyncSession) -> dict:
    """Analyze losing pattern and suggest improvements."""
    result = await db.execute(
        select(TradeSignal)
        .where(TradeSignal.status.in_(["hit_target", "stopped", "expired"]))
        .order_by(TradeSignal.created_at.desc())
        .limit(50)
    )
    recent = result.scalars().all()

    if len(recent) < 5:
        return {"analysis": "بيانات غير كافية للتحليل (أقل من 5 صفقات مغلقة)", "issues": [], "recommendations": []}

    stops = [s for s in recent if s.status == "stopped"]
    hits = [s for s in recent if s.status == "hit_target"]
    expired = [s for s in recent if s.status == "expired"]
    total = len(recent)

    loss_rate = len(stops) / total * 100
    issues = []
    recommendations = []

    # Check loss rate
    if loss_rate > 50:
        issues.append(f"⚠️ نسبة وقف الخسارة مرتفعة: {loss_rate:.0f}% ({len(stops)} من {total})")
        recommendations.append("🔧 تضييق وقف الخسارة أو زيادة المسافة")

    # Check if expired signals are too many
    if len(expired) / total > 0.3:
        issues.append(f"⏰ {len(expired)} توصيات انتهت بدون تحقيق هدف ({len(expired)/total*100:.0f}%)")
        recommendations.append("🔧 زيادة مدة التوصيات أو تقريب الأهداف")

    # Analyze by signal type
    long_stops = [s for s in stops if s.signal_type == "long"]
    short_stops = [s for s in stops if s.signal_type == "short"]
    long_total = len([s for s in recent if s.signal_type == "long"])
    short_total = len([s for s in recent if s.signal_type == "short"])

    if long_total > 3 and len(long_stops) / long_total > 0.6:
        issues.append(f"📈 صفقات Long تخسر بنسبة عالية: {len(long_stops)}/{long_total}")
        recommendations.append("🔧 تقليل صفقات الشراء أو تحسين نقاط الدخول")

    if short_total > 3 and len(short_stops) / short_total > 0.6:
        issues.append(f"📉 صفقات Short تخسر بنسبة عالية: {len(short_stops)}/{short_total}")
        recommendations.append("🔧 تقليل صفقات البيع أو انتظار تأكيدات أقوى")

    # Check confidence correlation
    low_conf_losses = [s for s in stops if float(s.confidence) < 50]
    if len(low_conf_losses) > len(stops) * 0.5:
        issues.append(f"🎯 {len(low_conf_losses)} خسائر كانت بثقة منخفضة (<50%)")
        recommendations.append("🔧 رفع الحد الأدنى للثقة المطلوبة للتوصيات")

    # Check symbols with most losses
    symbol_losses = {}
    for s in stops:
        symbol_losses[s.symbol] = symbol_losses.get(s.symbol, 0) + 1
    worst_symbols = sorted(symbol_losses.items(), key=lambda x: x[1], reverse=True)[:3]
    for sym, count in worst_symbols:
        if count >= 3:
            issues.append(f"💥 {sym} سجلت {count} خسائر")
            recommendations.append(f"🔧 مراجعة تحليل {sym} أو تقليل التداول عليها")

    if not issues:
        issues.append("✅ أداء البوت ضمن الحدود المقبولة")

    if not recommendations:
        recommendations.append("✅ لا توجد توصيات تحسين حالياً")

    return {
        "analysis": f"تحليل آخر {total} توصية — نسبة النجاح: {len(hits)/total*100:.0f}% | الخسارة: {loss_rate:.0f}%",
        "total_analyzed": total,
        "success_count": len(hits),
        "loss_count": len(stops),
        "expired_count": len(expired),
        "success_rate": round(len(hits) / total * 100, 1),
        "loss_rate": round(loss_rate, 1),
        "issues": issues,
        "recommendations": recommendations,
        "worst_symbols": worst_symbols,
    }
