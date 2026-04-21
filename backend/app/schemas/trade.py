from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TradeResponse(BaseModel):
    id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float
    total_value: float
    fee: float
    status: str
    executed_by: str
    created_at: datetime
    executed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AutoTradeToggle(BaseModel):
    is_auto_trade_enabled: bool


class TradeLimitsUpdate(BaseModel):
    max_trades_per_day: Optional[int] = None
    max_trade_amount: Optional[float] = None
    max_portfolio_percentage: Optional[float] = None
    max_daily_loss: Optional[float] = None
    min_loss_limit: Optional[float] = None
    max_loss_limit: Optional[float] = None
    min_confidence: Optional[float] = None
    signal_duration_multiplier: Optional[float] = None
    trade_size_pct: Optional[float] = None
    max_open_positions: Optional[int] = None


class BotSettingsResponse(BaseModel):
    is_auto_trade_enabled: bool
    is_admin_approved: bool
    max_trades_per_day: int
    max_trade_amount: float
    max_portfolio_percentage: float
    max_daily_loss: float
    min_loss_limit: float
    max_loss_limit: float
    min_confidence: float
    signal_duration_multiplier: float
    trade_size_pct: float = 20
    max_open_positions: int = 5
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
