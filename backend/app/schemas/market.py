from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class NewsSourceCreate(BaseModel):
    name: str
    url: Optional[str] = None
    is_active: bool = True


class NewsSourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    is_active: Optional[bool] = None


class NewsSourceResponse(BaseModel):
    id: str
    name: str
    url: Optional[str] = None
    is_active: bool
    is_suggested: bool
    created_at: datetime

    class Config:
        from_attributes = True


class SymbolCreate(BaseModel):
    symbol: str
    base_asset: str
    quote_asset: str = "USDT"
    is_default: bool = False
    is_active: bool = True
    min_trade_amount: Optional[float] = None


class SymbolUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    min_trade_amount: Optional[float] = None


class SymbolResponse(BaseModel):
    id: str
    symbol: str
    base_asset: str
    quote_asset: str
    is_default: bool
    is_active: bool
    min_trade_amount: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SuggestedCoin(BaseModel):
    symbol: str
    name: str
    current_price: float
    market_cap: float
    price_change_24h: float
    volume_24h: float
