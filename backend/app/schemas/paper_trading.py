from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ===== Paper Wallet =====

class PaperWalletCreate(BaseModel):
    initial_balance: float = 10000
    label: str = "المحفظة الوهمية"

class PaperWalletResponse(BaseModel):
    id: str
    label: str
    initial_balance: float
    current_balance: float
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class PaperHoldingResponse(BaseModel):
    id: str
    symbol: str
    asset: str
    quantity: float
    avg_buy_price: float
    class Config:
        from_attributes = True

class PaperWalletDetail(BaseModel):
    wallet: PaperWalletResponse
    holdings: List[PaperHoldingResponse]
    total_pnl: float
    total_pnl_pct: float
    win_rate: float
    total_trades: int


# ===== Paper Trade =====

class PaperTradeResponse(BaseModel):
    id: str
    symbol: str
    side: str
    quantity: float
    price: float
    total_value: float
    pnl: Optional[float] = 0
    status: str
    executed_by: str
    created_at: datetime
    class Config:
        from_attributes = True

class PaperManualTrade(BaseModel):
    symbol: str
    side: str  # buy | sell
    amount_usdt: float


# ===== Paper Bot Settings =====

class PaperBotSettingsResponse(BaseModel):
    is_enabled: bool
    max_trades_per_day: int
    max_trade_amount: float
    max_portfolio_percentage: float
    max_daily_loss: float
    min_loss_limit: float
    max_loss_limit: float
    min_confidence: float
    signal_duration_multiplier: float
    updated_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class PaperBotSettingsUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    max_trades_per_day: Optional[int] = None
    max_trade_amount: Optional[float] = None
    max_portfolio_percentage: Optional[float] = None
    max_daily_loss: Optional[float] = None
    min_loss_limit: Optional[float] = None
    max_loss_limit: Optional[float] = None
    min_confidence: Optional[float] = None
    signal_duration_multiplier: Optional[float] = None


# ===== Trade Signals =====

class TradeSignalResponse(BaseModel):
    id: str
    symbol: str
    signal_type: str
    timeframe_type: str
    entry_price: float
    target_1: float
    target_2: Optional[float] = None
    target_3: Optional[float] = None
    stop_loss: float
    confidence: float
    reasoning: str
    status: str
    hit_target_level: Optional[int] = None
    technical_data: Optional[dict] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    class Config:
        from_attributes = True
