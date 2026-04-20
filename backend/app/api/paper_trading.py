"""
Paper Trading & Signals API
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from typing import List, Optional
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.paper_trading import (
    PaperWallet, PaperHolding, PaperTrade, PaperBotSettings, TradeSignal
)
from app.schemas.paper_trading import (
    PaperWalletCreate, PaperWalletResponse, PaperWalletDetail,
    PaperHoldingResponse, PaperTradeResponse, PaperManualTrade,
    PaperBotSettingsResponse, PaperBotSettingsUpdate, TradeSignalResponse,
)
from app.services.paper_trader import execute_paper_trade
from app.services.binance_client import get_prices_batch

router = APIRouter(prefix="/api/paper", tags=["Paper Trading"])


# ===== Paper Wallet =====

@router.post("/wallet", response_model=PaperWalletResponse)
async def create_paper_wallet(
    data: PaperWalletCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new paper wallet with custom starting balance."""
    # Check if user already has an active wallet
    result = await db.execute(
        select(PaperWallet).where(PaperWallet.user_id == user.id, PaperWallet.is_active == True)
    )
    existing = result.scalars().first()
    if existing:
        raise HTTPException(400, "لديك محفظة وهمية نشطة بالفعل. قم بحذفها أولاً")

    wallet = PaperWallet(
        user_id=user.id,
        initial_balance=data.initial_balance,
        current_balance=data.initial_balance,
        label=data.label,
    )
    db.add(wallet)
    await db.commit()
    await db.refresh(wallet)
    return wallet


@router.get("/wallet", response_model=PaperWalletDetail)
async def get_paper_wallet(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paper wallet with holdings and performance stats."""
    result = await db.execute(
        select(PaperWallet).where(PaperWallet.user_id == user.id, PaperWallet.is_active == True)
    )
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(404, "لا توجد محفظة وهمية. قم بإنشاء واحدة")

    # Get holdings
    h_result = await db.execute(
        select(PaperHolding).where(PaperHolding.wallet_id == wallet.id)
    )
    holdings = h_result.scalars().all()

    # Get current prices for holdings value
    holdings_value = 0
    if holdings:
        try:
            symbols = [h.symbol for h in holdings]
            prices = await get_prices_batch(symbols)
            holdings_value = sum(float(h.quantity) * prices.get(h.symbol, 0) for h in holdings)
        except Exception:
            pass

    total_value = float(wallet.current_balance) + holdings_value
    total_pnl = total_value - float(wallet.initial_balance)
    total_pnl_pct = (total_pnl / float(wallet.initial_balance)) * 100 if float(wallet.initial_balance) > 0 else 0

    # Win rate
    trades_result = await db.execute(
        select(PaperTrade).where(
            PaperTrade.wallet_id == wallet.id,
            PaperTrade.side == "sell",
        )
    )
    sell_trades = trades_result.scalars().all()
    wins = sum(1 for t in sell_trades if float(t.pnl or 0) > 0)
    win_rate = (wins / len(sell_trades) * 100) if sell_trades else 0

    # Total trades count
    count_result = await db.execute(
        select(func.count(PaperTrade.id)).where(PaperTrade.wallet_id == wallet.id)
    )
    total_trades = count_result.scalar() or 0

    return PaperWalletDetail(
        wallet=PaperWalletResponse.model_validate(wallet),
        holdings=[PaperHoldingResponse.model_validate(h) for h in holdings],
        total_pnl=round(total_pnl, 2),
        total_pnl_pct=round(total_pnl_pct, 2),
        win_rate=round(win_rate, 1),
        total_trades=total_trades,
    )


@router.delete("/wallet")
async def delete_paper_wallet(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete paper wallet and reset."""
    result = await db.execute(
        select(PaperWallet).where(PaperWallet.user_id == user.id, PaperWallet.is_active == True)
    )
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(404, "لا توجد محفظة وهمية")

    await db.delete(wallet)
    await db.commit()
    return {"message": "تم حذف المحفظة الوهمية"}


@router.post("/wallet/reset", response_model=PaperWalletResponse)
async def reset_paper_wallet(
    data: PaperWalletCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset paper wallet with new balance."""
    result = await db.execute(
        select(PaperWallet).where(PaperWallet.user_id == user.id, PaperWallet.is_active == True)
    )
    wallet = result.scalar_one_or_none()
    if wallet:
        await db.delete(wallet)
        await db.flush()

    new_wallet = PaperWallet(
        user_id=user.id,
        initial_balance=data.initial_balance,
        current_balance=data.initial_balance,
        label=data.label,
    )
    db.add(new_wallet)
    await db.commit()
    await db.refresh(new_wallet)
    return new_wallet


# ===== Paper Trades =====

@router.post("/trade")
async def manual_paper_trade(
    data: PaperManualTrade,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute a manual paper trade."""
    result = await db.execute(
        select(PaperWallet).where(PaperWallet.user_id == user.id, PaperWallet.is_active == True)
    )
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(404, "لا توجد محفظة وهمية")

    trade_result = await execute_paper_trade(
        user_id=user.id,
        wallet=wallet,
        symbol=data.symbol,
        side=data.side,
        amount_usdt=data.amount_usdt,
        db=db,
        executed_by="manual",
    )
    await db.commit()

    if not trade_result["success"]:
        raise HTTPException(400, trade_result["error"])

    return trade_result


@router.get("/trades", response_model=List[PaperTradeResponse])
async def get_paper_trades(
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paper trade history."""
    result = await db.execute(
        select(PaperTrade)
        .where(PaperTrade.user_id == user.id)
        .order_by(desc(PaperTrade.created_at))
        .limit(limit)
    )
    return result.scalars().all()


# ===== Paper Bot Settings =====

@router.get("/bot-settings", response_model=PaperBotSettingsResponse)
async def get_paper_bot_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PaperBotSettings).where(PaperBotSettings.user_id == user.id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = PaperBotSettings(user_id=user.id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


@router.patch("/bot-settings", response_model=PaperBotSettingsResponse)
async def update_paper_bot_settings(
    data: PaperBotSettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PaperBotSettings).where(PaperBotSettings.user_id == user.id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = PaperBotSettings(user_id=user.id)
        db.add(settings)

    if data.is_enabled is not None:
        settings.is_enabled = data.is_enabled
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
    if data.min_confidence is not None:
        settings.min_confidence = data.min_confidence
    if data.signal_duration_multiplier is not None:
        settings.signal_duration_multiplier = data.signal_duration_multiplier

    await db.commit()
    await db.refresh(settings)
    return settings


# ===== Trade Signals =====

@router.get("/signals", response_model=List[TradeSignalResponse])
async def get_signals(
    status: Optional[str] = Query(default=None, description="active|hit_target|stopped|expired"),
    timeframe_type: Optional[str] = Query(default=None, description="short_term|long_term"),
    symbol: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get trade signals/recommendations."""
    query = select(TradeSignal).order_by(desc(TradeSignal.created_at)).limit(limit)
    if status:
        query = query.where(TradeSignal.status == status)
    if timeframe_type:
        query = query.where(TradeSignal.timeframe_type == timeframe_type)
    if symbol:
        query = query.where(TradeSignal.symbol == symbol)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/signals/active", response_model=List[TradeSignalResponse])
async def get_active_signals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get only active signals."""
    result = await db.execute(
        select(TradeSignal)
        .where(TradeSignal.status == "active")
        .order_by(desc(TradeSignal.confidence))
    )
    return result.scalars().all()


@router.post("/signals/generate")
async def trigger_signal_generation(
    timeframe: str = Query(default="1h", description="1m,5m,15m,30m,1h,4h,1d,1w"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger signal generation with custom timeframe."""
    import traceback
    from app.services.signal_generator import generate_signals_live, update_signal_statuses
    valid_tf = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]
    if timeframe not in valid_tf:
        raise HTTPException(400, f"فريم غير صالح. الخيارات: {', '.join(valid_tf)}")
    try:
        await update_signal_statuses(db)
        generated = await generate_signals_live(db, timeframe)
        return {"message": f"تم توليد {len(generated)} توصية جديدة ({timeframe})", "signals": generated}
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Signal generation error: {traceback.format_exc()}")
        raise HTTPException(500, f"خطأ في التوليد: {str(e)}")


@router.get("/signals/performance")
async def get_signal_performance_stats(
    symbol: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get signal performance statistics."""
    from app.services.signal_generator import get_signal_performance
    return await get_signal_performance(db, symbol)


@router.get("/signals/history/{symbol}")
async def get_signal_history_for_symbol(
    symbol: str,
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get signal history for a specific symbol."""
    result = await db.execute(
        select(TradeSignal)
        .where(TradeSignal.symbol == symbol)
        .order_by(desc(TradeSignal.created_at))
        .limit(limit)
    )
    signals = result.scalars().all()

    # Calculate PnL for each closed signal
    history = []
    for s in signals:
        entry = float(s.entry_price)
        pnl_pct = 0
        if s.status == "hit_target" and s.hit_target_level:
            target_val = float(getattr(s, f"target_{s.hit_target_level}", entry))
            pnl_pct = abs(target_val - entry) / entry * 100
        elif s.status == "stopped":
            pnl_pct = -abs(float(s.stop_loss) - entry) / entry * 100

        history.append({
            "id": s.id, "symbol": s.symbol, "signal_type": s.signal_type,
            "timeframe_type": s.timeframe_type, "entry_price": entry,
            "target_1": float(s.target_1), "target_2": float(s.target_2) if s.target_2 else None,
            "target_3": float(s.target_3) if s.target_3 else None,
            "stop_loss": float(s.stop_loss), "confidence": float(s.confidence),
            "status": s.status, "hit_target_level": s.hit_target_level,
            "pnl_pct": round(pnl_pct, 2),
            "reasoning": s.reasoning,
            "technical_data": s.technical_data,
            "created_at": str(s.created_at) if s.created_at else None,
            "expires_at": str(s.expires_at) if s.expires_at else None,
            "closed_at": str(s.closed_at) if s.closed_at else None,
        })
    return history


@router.get("/signals/bot-analysis")
async def get_bot_loss_analysis(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyze bot decisions and identify issues when losses increase."""
    from app.services.signal_generator import analyze_bot_losses
    return await analyze_bot_losses(db)


@router.delete("/signals/reset")
async def reset_signal_performance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all signals and reset performance data."""
    from sqlalchemy import delete
    result = await db.execute(delete(TradeSignal))
    await db.commit()
    return {"message": f"✅ تم حذف {result.rowcount} توصية وإعادة تعيين الأداء"}


@router.get("/signals/archive")
async def get_archived_signals(
    status_filter: Optional[str] = Query(None, description="hit_target|stopped|expired"),
    limit: int = Query(default=100, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get archived (closed) signals with full details for performance review."""
    query = select(TradeSignal).where(
        TradeSignal.status != "active"
    ).order_by(desc(TradeSignal.closed_at))

    if status_filter:
        query = query.where(TradeSignal.status == status_filter)

    result = await db.execute(query.limit(limit))
    signals = result.scalars().all()

    # Get current prices for comparison
    symbols_list = list(set(s.symbol for s in signals))
    try:
        current_prices = await get_prices_batch(symbols_list) if symbols_list else {}
    except Exception:
        current_prices = {}

    archive = []
    for s in signals:
        entry = float(s.entry_price)
        current = current_prices.get(s.symbol, 0)
        pnl_pct = 0
        if s.status == "hit_target" and s.hit_target_level:
            target_val = float(getattr(s, f"target_{s.hit_target_level}", entry))
            pnl_pct = abs(target_val - entry) / entry * 100
        elif s.status == "stopped":
            pnl_pct = -abs(float(s.stop_loss) - entry) / entry * 100

        archive.append({
            "id": s.id, "symbol": s.symbol, "signal_type": s.signal_type,
            "timeframe_type": s.timeframe_type, "entry_price": entry,
            "target_1": float(s.target_1),
            "target_2": float(s.target_2) if s.target_2 else None,
            "target_3": float(s.target_3) if s.target_3 else None,
            "stop_loss": float(s.stop_loss), "confidence": float(s.confidence),
            "status": s.status, "hit_target_level": s.hit_target_level,
            "pnl_pct": round(pnl_pct, 2), "reasoning": s.reasoning,
            "current_price": current, "technical_data": s.technical_data,
            "created_at": str(s.created_at) if s.created_at else None,
            "expires_at": str(s.expires_at) if s.expires_at else None,
            "closed_at": str(s.closed_at) if s.closed_at else None,
        })
    return archive
