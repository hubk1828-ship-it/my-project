"""
Self-Learning Models — Stores dynamic weights, prediction logs, and performance history.
Ported from QAF W3 Bayesian Learning system.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Numeric, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ComponentWeight(Base):
    """Dynamic scoring weights — updated daily by Bayesian learning."""
    __tablename__ = "component_weights"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    component: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0.05)
    win_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PredictionLog(Base):
    """Every prediction is logged for outcome tracking and learning."""
    __tablename__ = "prediction_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(10), nullable=False)  # LONG | SHORT
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    tp: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    sl: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    market_regime: Mapped[str] = mapped_column(String(20), nullable=True)
    session: Mapped[str] = mapped_column(String(10), nullable=True)  # US | EU | ASIA

    # Component scores at time of prediction
    scores: Mapped[dict] = mapped_column(JSON, nullable=True)

    # Filled later by outcome tracker
    outcome: Mapped[str] = mapped_column(String(10), nullable=True, index=True)  # WIN | LOSS | EXPIRED
    close_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=True)
    pnl_pct: Mapped[float] = mapped_column(Numeric(10, 4), nullable=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class SymbolProfile(Base):
    """Per-symbol learned profile — accumulated from historical performance."""
    __tablename__ = "symbol_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    win_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=50.0)
    avg_win_pct: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    avg_loss_pct: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    best_timeframe: Mapped[str] = mapped_column(String(10), nullable=True)
    best_regime: Mapped[str] = mapped_column(String(20), nullable=True)
    best_session: Mapped[str] = mapped_column(String(10), nullable=True)
    sl_multiplier: Mapped[float] = mapped_column(Numeric(5, 2), default=1.50)
    tp_multiplier: Mapped[float] = mapped_column(Numeric(5, 2), default=1.62)
    confidence_bias: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PerformanceLog(Base):
    """Daily performance snapshot for historical tracking."""
    __tablename__ = "performance_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    date: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    expired: Mapped[int] = mapped_column(Integer, default=0)
    pnl_pct: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    win_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    weights_snapshot: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
