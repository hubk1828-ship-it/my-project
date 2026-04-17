from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.analysis import BotAnalysis
from app.models.trade import Trade, BotSettings
from app.schemas.analysis import AnalysisResponse
from app.schemas.trade import TradeResponse, AutoTradeToggle, TradeLimitsUpdate, BotSettingsResponse

router = APIRouter(prefix="/api", tags=["Analysis & Trades"])


# ===== Analysis Endpoints =====

@router.get("/analysis/today", response_model=List[AnalysisResponse])
async def get_today_analysis(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get today's analysis results."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
    result = await db.execute(
        select(BotAnalysis)
        .where(BotAnalysis.created_at >= today)
        .order_by(desc(BotAnalysis.created_at))
    )
    return result.scalars().all()


@router.get("/analysis/history", response_model=List[AnalysisResponse])
async def get_analysis_history(
    symbol: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get analysis history with optional symbol filter."""
    query = select(BotAnalysis).order_by(desc(BotAnalysis.created_at)).limit(limit)
    if symbol:
        query = query.where(BotAnalysis.symbol == symbol)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/analysis/live")
async def live_analysis(
    symbol: str = Query(..., description="e.g. BTCUSDT"),
    timeframe: str = Query(default="1h", description="1m,5m,15m,30m,1h,4h,1d,1w"),
    user: User = Depends(get_current_user),
):
    """Run on-demand analysis for a symbol with custom timeframe (not saved to DB)."""
    from app.services.analyzer import analyze_chart, check_momentum
    valid_tf = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]
    if timeframe not in valid_tf:
        from fastapi import HTTPException
        raise HTTPException(400, f"فريم غير صالح. الخيارات: {', '.join(valid_tf)}")
    chart = await analyze_chart(symbol, timeframe)
    momentum = await check_momentum(symbol)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "trend": chart.get("trend"),
        "rsi": chart.get("rsi"),
        "ema20": chart.get("ema20"),
        "ema50": chart.get("ema50"),
        "support": chart.get("support"),
        "resistance": chart.get("resistance"),
        "current_price": chart.get("current_price"),
        "volume_ratio": momentum.get("ratio"),
        "smc": chart.get("smc"),
        "smc_signal": chart.get("smc_signal"),
    }


# ===== Trade Endpoints =====

@router.get("/trades", response_model=List[TradeResponse])
async def get_trades(
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's trade history."""
    result = await db.execute(
        select(Trade)
        .where(Trade.user_id == user.id)
        .order_by(desc(Trade.created_at))
        .limit(limit)
    )
    return result.scalars().all()


# ===== Bot Settings Endpoints =====

@router.get("/settings/bot", response_model=BotSettingsResponse)
async def get_bot_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's bot/auto-trade settings."""
    result = await db.execute(select(BotSettings).where(BotSettings.user_id == user.id))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = BotSettings(user_id=user.id)
        db.add(settings)
        await db.flush()
    return settings


@router.patch("/settings/auto-trade", response_model=BotSettingsResponse)
async def toggle_auto_trade(
    data: AutoTradeToggle,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle auto-trade on/off."""
    result = await db.execute(select(BotSettings).where(BotSettings.user_id == user.id))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = BotSettings(user_id=user.id)
        db.add(settings)

    settings.is_auto_trade_enabled = data.is_auto_trade_enabled
    await db.flush()
    return settings


@router.patch("/settings/limits", response_model=BotSettingsResponse)
async def update_limits(
    data: TradeLimitsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update trading limits."""
    result = await db.execute(select(BotSettings).where(BotSettings.user_id == user.id))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = BotSettings(user_id=user.id)
        db.add(settings)

    if data.max_trades_per_day is not None:
        settings.max_trades_per_day = data.max_trades_per_day
    if data.max_trade_amount is not None:
        settings.max_trade_amount = data.max_trade_amount
    if data.max_portfolio_percentage is not None:
        settings.max_portfolio_percentage = data.max_portfolio_percentage
    if data.max_daily_loss is not None:
        settings.max_daily_loss = data.max_daily_loss
    if data.min_loss_limit is not None:
        settings.min_loss_limit = data.min_loss_limit
    if data.max_loss_limit is not None:
        settings.max_loss_limit = data.max_loss_limit

    await db.flush()
    return settings
