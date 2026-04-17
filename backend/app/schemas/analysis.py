from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class AnalysisResponse(BaseModel):
    id: str
    symbol: str
    timeframe: str
    news_source: Optional[str]
    news_title: Optional[str]
    is_momentum_real: Optional[bool]
    price_confirmed_news: Optional[bool]
    decision: str
    confidence_score: Optional[float]
    reasoning: str
    technical_indicators: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationPrefUpdate(BaseModel):
    telegram_enabled: Optional[bool] = None
    telegram_chat_id: Optional[str] = None
    email_enabled: Optional[bool] = None
    web_enabled: Optional[bool] = None
    notify_opportunities: Optional[bool] = None
    notify_trades: Optional[bool] = None
    notify_daily_summary: Optional[bool] = None
