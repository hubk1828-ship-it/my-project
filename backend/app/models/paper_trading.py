"""
Paper Trading Models — Virtual trading bot with real market prices.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Integer, Numeric, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class PaperWallet(Base):
    """Virtual wallet with user-defined starting balance."""
    __tablename__ = "paper_wallets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), default="المحفظة الوهمية")
    initial_balance: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=10000)
    current_balance: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=10000)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="paper_wallets")
    holdings = relationship("PaperHolding", back_populates="wallet", cascade="all, delete-orphan")
    trades = relationship("PaperTrade", back_populates="wallet", cascade="all, delete-orphan")


class PaperHolding(Base):
    """Virtual crypto holdings in the paper wallet."""
    __tablename__ = "paper_holdings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    wallet_id: Mapped[str] = mapped_column(String(36), ForeignKey("paper_wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    asset: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=0)
    avg_buy_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=0)
    take_profit_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=True)
    stop_loss_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=True)
    signal_id: Mapped[str] = mapped_column(String(36), nullable=True)
    entry_trade_id: Mapped[str] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    wallet = relationship("PaperWallet", back_populates="holdings")


class PaperTrade(Base):
    """Virtual trade executed by the paper trading bot."""
    __tablename__ = "paper_trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    wallet_id: Mapped[str] = mapped_column(String(36), ForeignKey("paper_wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("bot_analyses.id", ondelete="SET NULL"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # buy | sell
    quantity: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    total_value: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    pnl: Mapped[float] = mapped_column(Numeric(20, 8), nullable=True, default=0)  # Profit/Loss for sells
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="filled")
    executed_by: Mapped[str] = mapped_column(String(10), nullable=False, default="paper_bot")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    wallet = relationship("PaperWallet", back_populates="trades")
    user = relationship("User", back_populates="paper_trades")


class PaperBotSettings(Base):
    """Settings for the paper trading bot."""
    __tablename__ = "paper_bot_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_trades_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_trade_amount: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=500)
    max_portfolio_percentage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=20.00)
    max_daily_loss: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=200)
    min_loss_limit: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=10)
    max_loss_limit: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=500)
    min_confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=40)
    signal_duration_multiplier: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=1.0)
    trade_size_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=20)
    max_open_positions: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="paper_bot_settings")


class TradeSignal(Base):
    """Trading recommendations/signals with targets for users."""
    __tablename__ = "trade_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(10), nullable=False)  # long | short
    timeframe_type: Mapped[str] = mapped_column(String(15), nullable=False)  # short_term | long_term
    entry_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    target_1: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    target_2: Mapped[float] = mapped_column(Numeric(20, 8), nullable=True)
    target_3: Mapped[float] = mapped_column(Numeric(20, 8), nullable=True)
    stop_loss: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=50)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default="active")  # active | hit_target | stopped | expired
    hit_target_level: Mapped[int] = mapped_column(Integer, nullable=True)  # 1, 2, or 3
    technical_data: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    close_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=True)
    pnl_percentage: Mapped[float] = mapped_column(Numeric(10, 4), nullable=True)
