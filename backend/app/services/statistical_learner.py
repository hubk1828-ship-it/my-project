"""
Statistical Self-Learning — Bayesian weight updating system.
Ported from QAF W3. NOT AI — pure statistics. Same data = same adjustments.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.learning import ComponentWeight, PredictionLog, SymbolProfile, PerformanceLog
from app.services.deterministic_engine import COMPONENTS, DEFAULT_WEIGHTS

logger = logging.getLogger(__name__)

BAYESIAN_NEW = 0.70  # Weight for new evidence
BAYESIAN_OLD = 0.30  # Weight for prior belief
MIN_FLOOR = 0.02     # Minimum weight per component
MIN_TRADES = 5       # Minimum trades before adjusting


async def load_weights(db: AsyncSession) -> Dict[str, float]:
    """Load dynamic weights from DB, fallback to defaults."""
    result = await db.execute(select(ComponentWeight))
    rows = result.scalars().all()
    if not rows or len(rows) < 4:
        return dict(DEFAULT_WEIGHTS)
    weights = {}
    for r in rows:
        if r.component in COMPONENTS:
            weights[r.component] = float(r.weight)
    total = sum(weights.values())
    if total < 0.3:
        return dict(DEFAULT_WEIGHTS)
    return weights


async def seed_weights(db: AsyncSession):
    """Initialize weights in DB if not present."""
    result = await db.execute(select(func.count(ComponentWeight.id)))
    count = result.scalar()
    if count == 0:
        for comp, w in DEFAULT_WEIGHTS.items():
            db.add(ComponentWeight(component=comp, weight=w))
        await db.commit()
        logger.info(f"✅ Seeded {len(DEFAULT_WEIGHTS)} component weights")


async def log_prediction(db: AsyncSession, signal: Dict):
    """Log a prediction for future outcome tracking."""
    log = PredictionLog(
        symbol=signal.get("symbol", ""),
        timeframe=signal.get("timeframe", "15m"),
        signal_type=signal.get("signal_type", "NEUTRAL"),
        confidence=signal.get("confidence", 0),
        entry_price=signal.get("price", 0),
        tp=signal.get("tp", 0),
        sl=signal.get("sl", 0),
        market_regime=signal.get("market_regime", ""),
        session=signal.get("session", ""),
        scores=signal.get("scores", {}),
        outcome="PENDING",
    )
    db.add(log)
    await db.flush()
    return log.id


async def evaluate_outcomes(db: AsyncSession, prices: Dict[str, float]):
    """Check pending predictions and mark WIN/LOSS/EXPIRED (from QAF W2)."""
    result = await db.execute(
        select(PredictionLog).where(PredictionLog.outcome == "PENDING")
    )
    pending = result.scalars().all()
    if not pending:
        return 0

    now = datetime.now(timezone.utc)
    updated = 0

    for pred in pending:
        price = prices.get(pred.symbol, 0)
        if price <= 0:
            continue

        entry = float(pred.entry_price)
        tp = float(pred.tp)
        sl = float(pred.sl)
        age_hours = (now - pred.created_at).total_seconds() / 3600 if pred.created_at else 0

        outcome = None
        pnl = 0.0
        close_price = price

        if pred.signal_type == "LONG":
            if price >= tp > 0:
                outcome = "WIN"
                pnl = ((tp - entry) / entry) * 100
                close_price = tp
            elif 0 < price <= sl:
                outcome = "LOSS"
                pnl = ((sl - entry) / entry) * 100
                close_price = sl
        elif pred.signal_type == "SHORT":
            if 0 < price <= tp:
                outcome = "WIN"
                pnl = ((entry - tp) / entry) * 100
                close_price = tp
            elif price >= sl > 0:
                outcome = "LOSS"
                pnl = ((entry - sl) / entry) * 100
                close_price = sl

        if not outcome and age_hours > 24:
            outcome = "EXPIRED"
            if pred.signal_type == "LONG":
                pnl = ((price - entry) / entry) * 100
            else:
                pnl = ((entry - price) / entry) * 100
            close_price = price

        if outcome:
            pred.outcome = outcome
            pred.pnl_pct = round(pnl, 4)
            pred.close_price = close_price
            pred.closed_at = now
            updated += 1

    if updated > 0:
        await db.commit()
        logger.info(f"📊 Evaluated {updated} prediction outcomes")
    return updated


async def run_bayesian_learning(db: AsyncSession) -> Dict:
    """
    Bayesian weight update — runs daily (from QAF W3).
    For each component: new_weight = 0.70 * win_rate + 0.30 * old_weight
    Then normalize so all weights sum to 1.0.
    """
    # Load all closed predictions
    result = await db.execute(
        select(PredictionLog).where(
            PredictionLog.outcome.in_(["WIN", "LOSS"])
        )
    )
    all_closed = result.scalars().all()

    if len(all_closed) < MIN_TRADES:
        logger.info(f"📊 Not enough trades for learning ({len(all_closed)} < {MIN_TRADES})")
        return {"status": "insufficient_data", "total": len(all_closed)}

    # Load current weights
    current_weights = await load_weights(db)

    # Calculate win rate per component
    comp_stats = {}
    for comp in COMPONENTS:
        key = comp
        relevant = [t for t in all_closed if t.scores and t.scores.get(key) is not None and float(t.scores.get(key, 0)) > 0]
        wins = len([t for t in relevant if t.outcome == "WIN"])
        total = len(relevant)
        win_rate = wins / total if total >= MIN_TRADES else 0.5
        comp_stats[comp] = {"wins": wins, "total": total, "win_rate": win_rate}

    # Bayesian blend
    new_weights = {}
    for comp in COMPONENTS:
        cur = current_weights.get(comp, 0.05)
        blended = BAYESIAN_NEW * comp_stats[comp]["win_rate"] + BAYESIAN_OLD * cur
        new_weights[comp] = max(MIN_FLOOR, blended)

    # Normalize
    w_sum = sum(new_weights.values())
    for comp in COMPONENTS:
        new_weights[comp] = round(new_weights[comp] / w_sum, 6)

    # Save to DB
    for comp in COMPONENTS:
        result = await db.execute(
            select(ComponentWeight).where(ComponentWeight.component == comp)
        )
        row = result.scalar_one_or_none()
        if row:
            row.weight = new_weights[comp]
            row.win_rate = round(comp_stats[comp]["win_rate"] * 100, 2)
            row.total_trades = comp_stats[comp]["total"]
        else:
            db.add(ComponentWeight(
                component=comp,
                weight=new_weights[comp],
                win_rate=round(comp_stats[comp]["win_rate"] * 100, 2),
                total_trades=comp_stats[comp]["total"],
            ))

    await db.commit()
    logger.info(f"🧠 Bayesian learning complete — updated {len(COMPONENTS)} weights")
    return {"status": "updated", "weights": new_weights, "stats": comp_stats}


async def update_symbol_profiles(db: AsyncSession):
    """Update per-symbol learned profiles based on prediction history."""
    result = await db.execute(
        select(PredictionLog.symbol).where(
            PredictionLog.outcome.in_(["WIN", "LOSS"])
        ).distinct()
    )
    symbols = [r for r in result.scalars().all()]

    for symbol in symbols:
        result = await db.execute(
            select(PredictionLog).where(
                PredictionLog.symbol == symbol,
                PredictionLog.outcome.in_(["WIN", "LOSS"]),
            )
        )
        trades = result.scalars().all()
        if len(trades) < MIN_TRADES:
            continue

        wins = [t for t in trades if t.outcome == "WIN"]
        losses = [t for t in trades if t.outcome == "LOSS"]
        total = len(trades)
        win_rate = len(wins) / total * 100

        avg_win = sum(float(t.pnl_pct or 0) for t in wins) / len(wins) if wins else 0
        avg_loss = sum(float(t.pnl_pct or 0) for t in losses) / len(losses) if losses else 0

        # Find best timeframe
        tf_wins = {}
        for t in trades:
            tf = t.timeframe or "15m"
            if tf not in tf_wins:
                tf_wins[tf] = {"w": 0, "t": 0}
            tf_wins[tf]["t"] += 1
            if t.outcome == "WIN":
                tf_wins[tf]["w"] += 1
        best_tf = max(tf_wins, key=lambda k: tf_wins[k]["w"] / tf_wins[k]["t"] if tf_wins[k]["t"] >= 3 else 0)

        # Adjust SL/TP multipliers based on performance
        sl_mul = 1.5
        tp_mul = 1.618
        loss_rate = len(losses) / total
        if loss_rate > 0.6:
            sl_mul = 2.0  # Widen SL if too many stops
        if avg_win > 0 and avg_loss < 0 and abs(avg_win) < abs(avg_loss):
            tp_mul = 1.3  # Bring TP closer if wins are small

        # Confidence bias
        conf_bias = 0
        if win_rate > 65:
            conf_bias = 3  # Boost confident symbols
        elif win_rate < 35:
            conf_bias = -5  # Penalize losing symbols

        # Upsert profile
        result = await db.execute(
            select(SymbolProfile).where(SymbolProfile.symbol == symbol)
        )
        profile = result.scalar_one_or_none()
        if profile:
            profile.win_rate = win_rate
            profile.avg_win_pct = avg_win
            profile.avg_loss_pct = avg_loss
            profile.best_timeframe = best_tf
            profile.sl_multiplier = sl_mul
            profile.tp_multiplier = tp_mul
            profile.confidence_bias = conf_bias
            profile.total_trades = total
        else:
            db.add(SymbolProfile(
                symbol=symbol, win_rate=win_rate,
                avg_win_pct=avg_win, avg_loss_pct=avg_loss,
                best_timeframe=best_tf, sl_multiplier=sl_mul,
                tp_multiplier=tp_mul, confidence_bias=conf_bias,
                total_trades=total,
            ))

    await db.commit()
    logger.info(f"📊 Updated {len(symbols)} symbol profiles")


async def save_daily_performance(db: AsyncSession):
    """Save daily performance log snapshot."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Check if already logged today
    result = await db.execute(
        select(PerformanceLog).where(PerformanceLog.date == today)
    )
    if result.scalar_one_or_none():
        return

    # Get today's predictions
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(PredictionLog).where(PredictionLog.created_at >= start)
    )
    today_preds = result.scalars().all()

    wins = len([p for p in today_preds if p.outcome == "WIN"])
    losses = len([p for p in today_preds if p.outcome == "LOSS"])
    expired = len([p for p in today_preds if p.outcome == "EXPIRED"])
    total = wins + losses
    pnl = sum(float(p.pnl_pct or 0) for p in today_preds if p.outcome in ("WIN", "LOSS"))

    weights = await load_weights(db)

    db.add(PerformanceLog(
        date=today,
        wins=wins,
        losses=losses,
        expired=expired,
        pnl_pct=round(pnl, 4),
        win_rate=round(wins / total * 100, 2) if total > 0 else 0,
        weights_snapshot=weights,
    ))
    await db.commit()
    logger.info(f"📅 Daily performance saved: {wins}W/{losses}L, PnL: {pnl:.2f}%")
