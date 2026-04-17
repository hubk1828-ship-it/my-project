from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class WalletConnect(BaseModel):
    exchange: str  # binance | bybit
    api_key: str
    api_secret: str
    label: Optional[str] = None


class WalletResponse(BaseModel):
    id: str
    exchange: str
    label: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class BalanceItem(BaseModel):
    asset: str
    free_balance: float
    locked_balance: float
    usd_value: Optional[float] = None


class WalletBalanceResponse(BaseModel):
    wallet_id: str
    exchange: str
    total_usd: float
    assets: List[BalanceItem]
