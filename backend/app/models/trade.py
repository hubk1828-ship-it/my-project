import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Integer, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class BotSettings(Base):
    __tablename__ = "bot_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    is_auto_trade_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_admin_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_trades_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_trade_amount: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=100)
    max_portfolio_percentage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=10.00)
    max_daily_loss: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=50)
    min_loss_limit: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=10)
    max_loss_limit: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=200)
    min_confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=40)
    signal_duration_multiplier: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=1.0)
    trade_size_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=20)
    max_open_positions: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="bot_settings")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    wallet_id: Mapped[str] = mapped_column(String(36), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("bot_analyses.id", ondelete="SET NULL"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # buy | sell
    order_type: Mapped[str] = mapped_column(String(10), nullable=False, default="market")
    quantity: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    total_value: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    fee: Mapped[float] = mapped_column(Numeric(20, 8), default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    executed_by: Mapped[str] = mapped_column(String(10), nullable=False)  # bot | manual
    exchange_order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="trades")
    wallet = relationship("Wallet", back_populates="trades")


class SupportedSymbol(Base):
    __tablename__ = "supported_symbols"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    base_asset: Mapped[str] = mapped_column(String(10), nullable=False)
    quote_asset: Mapped[str] = mapped_column(String(10), nullable=False, default="USDT")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min_trade_amount: Mapped[float] = mapped_column(Numeric(20, 8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TrustedNewsSource(Base):
    __tablename__ = "trusted_news_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_suggested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
