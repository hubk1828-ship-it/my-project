"""
Risk Manager — Mathematical position sizing and portfolio protection.
Kelly Criterion, Drawdown limits, Correlation filter, Cooldown.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

logger = logging.getLogger("risk_manager")

# ===== Kelly Criterion =====

def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Kelly Criterion: f* = (bp - q) / b
    b = avg_win / avg_loss
    p = win_rate, q = 1 - p
    Returns Half-Kelly for safety.
    """
    if avg_loss <= 0 or win_rate <= 0:
        return 0.01  # minimum 1%

    b = avg_win / avg_loss
    p = min(win_rate, 0.99)
    q = 1.0 - p

    f = (b * p - q) / b
    f = max(0.005, min(f, 0.25))  # clamp 0.5% to 25%

    return round(f / 2, 4)  # Half-Kelly for safety


# ===== Position Sizing =====

def calculate_position_size(
    portfolio_balance: float,
    atr_value: float,
    current_price: float,
    risk_pct: float = 0.01,
    win_rate: float = 0.55,
    avg_win_pct: float = 0.8,
    avg_loss_pct: float = 0.5,
) -> dict:
    """
    ATR-based position sizing with Kelly Criterion.
    risk_amount = portfolio × risk_pct
    position_size = risk_amount / (ATR × 1.5)
    Capped by Kelly fraction.
    """
    if portfolio_balance <= 0 or atr_value <= 0 or current_price <= 0:
        return {"amount_usdt": 0, "reason": "Invalid inputs"}

    # Kelly
    kelly = kelly_fraction(win_rate, avg_win_pct, avg_loss_pct)
    max_by_kelly = portfolio_balance * kelly

    # ATR-based risk
    risk_amount = portfolio_balance * risk_pct
    stop_distance = atr_value * 1.5
    quantity = risk_amount / stop_distance
    amount_usdt = quantity * current_price

    # Cap by Kelly and absolute limits
    amount_usdt = min(amount_usdt, max_by_kelly)
    amount_usdt = min(amount_usdt, portfolio_balance * 0.15)  # max 15% per trade
    amount_usdt = max(amount_usdt, 5.0)  # minimum $5

    return {
        "amount_usdt": round(amount_usdt, 2),
        "kelly_fraction": kelly,
        "risk_pct": risk_pct,
        "stop_distance": round(stop_distance, 6),
    }


# ===== Drawdown Protection =====

async def check_drawdown(wallet, db: AsyncSession, max_drawdown_pct: float = 5.0) -> dict:
    """
    Check if portfolio drawdown exceeds limit.
    Drawdown = (peak - current) / peak × 100
    """
    current = float(wallet.current_balance)
    initial = float(wallet.initial_balance)

    if initial <= 0:
        return {"safe": True, "drawdown_pct": 0}

    # Peak = max of initial and any historical high
    peak = max(initial, current)  # simplified; ideally track peak separately
    drawdown_pct = ((peak - current) / peak) * 100 if peak > 0 else 0

    safe = drawdown_pct < max_drawdown_pct

    if not safe:
        logger.warning(f"🛑 Drawdown {drawdown_pct:.1f}% > {max_drawdown_pct}% — STOPPING")

    return {
        "safe": safe,
        "drawdown_pct": round(drawdown_pct, 2),
        "current": current,
        "peak": peak,
    }


# ===== Consecutive Loss Check =====

async def check_consecutive_losses(user_id: str, db: AsyncSession, max_consecutive: int = 3) -> dict:
    """Stop trading after N consecutive losses."""
    from app.models.paper_trading import PaperTrade

    result = await db.execute(
        select(PaperTrade)
        .where(
            PaperTrade.user_id == user_id,
            PaperTrade.side == "sell",
        )
        .order_by(PaperTrade.created_at.desc())
        .limit(max_consecutive)
    )
    recent_sells = result.scalars().all()

    consecutive = 0
    for trade in recent_sells:
        if float(trade.pnl or 0) < 0:
            consecutive += 1
        else:
            break

    safe = consecutive < max_consecutive

    if not safe:
        logger.warning(f"🛑 {consecutive} consecutive losses — cooling down")

    return {"safe": safe, "consecutive_losses": consecutive}


# ===== Cooldown Check =====

async def check_cooldown(wallet_id: str, symbol: str, db: AsyncSession, cooldown_minutes: int = 5) -> dict:
    """Prevent trading same symbol within cooldown period."""
    from app.models.paper_trading import PaperTrade

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
    result = await db.execute(
        select(PaperTrade).where(
            PaperTrade.wallet_id == wallet_id,
            PaperTrade.symbol == symbol,
            PaperTrade.created_at >= cutoff,
        ).limit(1)
    )
    recent = result.scalar_one_or_none()

    return {
        "can_trade": recent is None,
        "reason": f"Cooldown active ({cooldown_minutes}min)" if recent else "OK",
    }


# ===== Correlation Filter =====

CORRELATION_GROUPS = {
    "BTC_GROUP": ["BTCUSDT"],
    "ETH_GROUP": ["ETHUSDT"],
    "ALT_HIGH": ["BNBUSDT", "SOLUSDT"],
    "ALT_MID": ["XRPUSDT", "ADAUSDT", "LINKUSDT", "DOTUSDT"],
}


def check_correlation(symbol: str, existing_holdings: list, max_same_group: int = 2) -> dict:
    """Prevent over-concentration in correlated assets."""
    symbol_group = None
    for group, symbols in CORRELATION_GROUPS.items():
        if symbol in symbols:
            symbol_group = group
            break

    if not symbol_group:
        return {"approved": True, "reason": "No correlation group"}

    same_group = [h for h in existing_holdings if h in CORRELATION_GROUPS.get(symbol_group, [])]

    approved = len(same_group) < max_same_group

    return {
        "approved": approved,
        "reason": f"Already holding {len(same_group)} from {symbol_group}" if not approved else "OK",
        "group": symbol_group,
    }


# ===== Master Validation =====

async def validate_trade(
    symbol: str,
    side: str,
    wallet,
    user_id: str,
    db: AsyncSession,
    atr_value: float = 0,
    current_price: float = 0,
    existing_holdings: list = None,
) -> dict:
    """
    Full pre-trade validation:
    1. Drawdown check
    2. Consecutive loss check
    3. Cooldown check
    4. Correlation check
    5. Position sizing
    """
    # 1. Drawdown
    dd = await check_drawdown(wallet, db)
    if not dd["safe"]:
        return {"approved": False, "reason": f"🛑 Drawdown {dd['drawdown_pct']}% — trading stopped", "amount": 0}

    # 2. Consecutive losses
    cl = await check_consecutive_losses(user_id, db)
    if not cl["safe"]:
        return {"approved": False, "reason": f"🛑 {cl['consecutive_losses']} consecutive losses", "amount": 0}

    # 3. Cooldown
    cd = await check_cooldown(wallet.id, symbol, db)
    if not cd["can_trade"]:
        return {"approved": False, "reason": f"⏳ {cd['reason']}", "amount": 0}

    # 4. Correlation
    if existing_holdings and side == "buy":
        corr = check_correlation(symbol, existing_holdings)
        if not corr["approved"]:
            return {"approved": False, "reason": f"🔗 {corr['reason']}", "amount": 0}

    # 5. Position sizing
    if atr_value > 0 and current_price > 0:
        ps = calculate_position_size(float(wallet.current_balance), atr_value, current_price)
        amount = ps["amount_usdt"]
    else:
        # Fallback: 2% of portfolio
        amount = min(float(wallet.current_balance) * 0.02, 100)

    return {"approved": True, "reason": "✅ All checks passed", "amount": round(amount, 2)}
