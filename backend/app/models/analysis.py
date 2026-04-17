import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Numeric, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class BotAnalysis(Base):
    __tablename__ = "bot_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), default="1h")
    news_source: Mapped[str] = mapped_column(String(100), nullable=True)
    news_title: Mapped[str] = mapped_column(Text, nullable=True)
    news_url: Mapped[str] = mapped_column(Text, nullable=True)
    is_momentum_real: Mapped[bool] = mapped_column(Boolean, nullable=True)
    price_confirmed_news: Mapped[bool] = mapped_column(Boolean, nullable=True)
    decision: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # buy | sell | no_opportunity
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    technical_indicators: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
