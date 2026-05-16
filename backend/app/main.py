"""
CryptoAnalyzer — Main Application Entry Point
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import init_db, AsyncSessionLocal, engine
from app.core.security import hash_password

# Import all models to register with SQLAlchemy
from app.models.user import User
from app.models.wallet import Wallet, WalletBalance
from app.models.analysis import BotAnalysis
from app.models.trade import Trade, BotSettings, SupportedSymbol, TrustedNewsSource
from app.models.notification import Notification, UserNotificationPreference, RefreshToken
from app.models.paper_trading import PaperWallet, PaperHolding, PaperTrade, PaperBotSettings, TradeSignal
from app.models.learning import ComponentWeight, PredictionLog, SymbolProfile, PerformanceLog

# Import routers
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.wallets import router as wallets_router
from app.api.trades import router as trades_router
from app.api.notifications import router as notifications_router
from app.api.market import router as market_router
from app.api.ws import router as ws_router
from app.api.paper_trading import router as paper_router
from app.api.deps import require_admin

settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def run_analysis_job():
    """Scheduled job: deterministic analysis for all active symbols."""
    from app.services.deterministic_engine import analyze_symbol_deterministic
    from app.services.liquidity_analyzer import get_all_liquidity_data
    from app.services.statistical_learner import load_weights, log_prediction
    from app.services.notifier import send_notification, format_opportunity_alert
    from app.services.binance_client import get_prices_batch, BinanceClient
    import asyncio

    logger.info("📐 Starting deterministic analysis...")

    async with AsyncSessionLocal() as db:
        # Load dynamic weights from DB
        weights = await load_weights(db)

        # Get active symbols
        result = await db.execute(
            select(SupportedSymbol).where(SupportedSymbol.is_active == True)
        )
        symbols = result.scalars().all()

        # Get BTC klines once for correlation
        btc_klines = []
        try:
            client = BinanceClient("", "")
            btc_klines = await client.get_klines("BTCUSDT", "15m", 50)
        except Exception:
            pass

        for i, sym in enumerate(symbols):
            try:
                if i > 0:
                    await asyncio.sleep(3)

                # Fetch klines + liquidity data
                client = BinanceClient("", "")
                klines = await client.get_klines(sym.symbol, "15m", 100)
                liq_data = await get_all_liquidity_data(sym.symbol)

                # Load symbol profile
                profile_result = await db.execute(
                    select(SymbolProfile).where(SymbolProfile.symbol == sym.symbol)
                )
                profile = profile_result.scalar_one_or_none()
                profile_dict = None
                if profile:
                    profile_dict = {
                        "sl_multiplier": float(profile.sl_multiplier),
                        "tp_multiplier": float(profile.tp_multiplier),
                        "confidence_bias": float(profile.confidence_bias),
                    }

                # Run deterministic analysis
                signal = await analyze_symbol_deterministic(
                    symbol=sym.symbol,
                    klines_data=klines,
                    btc_klines_data=btc_klines,
                    weights=weights,
                    symbol_profile=profile_dict,
                    order_book=liq_data["order_book"],
                    funding_rate=liq_data["funding_rate"],
                    fear_greed=liq_data["fear_greed"],
                    ls_ratio=liq_data["ls_ratio"],
                    spot_price=liq_data["spot_price"],
                )

                # Map to BotAnalysis format for DB compatibility
                decision = "no_opportunity"
                sig_type = signal.get("signal_type", "NONE")
                if signal.get("should_trade"):
                    decision = "buy" if sig_type == "LONG" else "sell"
                elif signal.get("near_miss"):
                    decision = "buy" if sig_type == "LONG" else "sell"

                reasoning_parts = [
                    f"📐 تحليل حتمي | الثقة: {signal.get('confidence', 0)}%",
                    f"الاتجاه: {signal.get('trend_direction', 'N/A')} | النظام: {signal.get('market_regime', 'N/A')}",
                    f"RSI: {signal.get('rsi', 0)} | VWAP: {signal.get('vwap_position', 'N/A')}",
                    f"R:R = {signal.get('rr_ratio', 0)}:1 | الحجم: {signal.get('position_size', 'N/A')}",
                ]

                # Save to DB
                old = await db.execute(select(BotAnalysis).where(BotAnalysis.symbol == sym.symbol))
                for o in old.scalars().all():
                    await db.delete(o)

                analysis = BotAnalysis(
                    symbol=sym.symbol,
                    decision=decision,
                    confidence_score=signal.get("confidence", 0),
                    reasoning=" | ".join(reasoning_parts),
                    technical_indicators=signal,
                )
                db.add(analysis)

                # Log prediction for learning
                if signal.get("should_trade"):
                    await log_prediction(db, signal)

                await db.commit()
                logger.info(f"✅ {sym.symbol}: {decision} ({signal.get('confidence', 0)}%)")

            except Exception as e:
                logger.error(f"❌ Analysis failed for {sym.symbol}: {e}")

    logger.info("✅ Deterministic analysis cycle complete")


async def run_paper_bot_job():
    """Scheduled job: run paper trading bot for all enabled users."""
    from app.services.paper_trader import run_paper_bot_cycle
    logger.info("📄 Starting paper bot cycle...")
    async with AsyncSessionLocal() as db:
        await run_paper_bot_cycle(db)


async def run_price_monitor_job():
    """Runs every 5 seconds - checks targets/stops from WebSocket cache."""
    from app.services.price_monitor import run_price_monitor, run_paper_auto_buy
    try:
        async with AsyncSessionLocal() as db:
            await run_price_monitor(db)
            await run_paper_auto_buy(db)
    except Exception as e:
        logger.error(f"Price monitor error: {e}")


async def run_signals_job():
    """Scheduled job: generate trade signals, update statuses, and clean old analyses."""
    from app.services.signal_generator import generate_signals, update_signal_statuses
    from sqlalchemy import delete, text
    from datetime import datetime, timezone, timedelta

    logger.info("🎯 Starting signal generation...")
    async with AsyncSessionLocal() as db:
        await update_signal_statuses(db)
        await generate_signals(db)

        # Auto-cleanup: remove analyses older than 24 hours
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            result = await db.execute(
                delete(BotAnalysis).where(BotAnalysis.created_at < cutoff)
            )
            if result.rowcount > 0:
                await db.commit()
                logger.info(f"🧹 Cleaned {result.rowcount} old analyses (>24h)")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")


async def run_learning_job():
    """Scheduled job: evaluate prediction outcomes + Bayesian weight update."""
    from app.services.statistical_learner import evaluate_outcomes, run_bayesian_learning, update_symbol_profiles, save_daily_performance
    from app.services.binance_client import get_prices_batch

    logger.info("🧠 Starting learning cycle...")
    async with AsyncSessionLocal() as db:
        # Get current prices
        result = await db.execute(select(SupportedSymbol).where(SupportedSymbol.is_active == True))
        symbols = [s.symbol for s in result.scalars().all()]
        prices = await get_prices_batch(symbols)

        # Evaluate pending predictions
        await evaluate_outcomes(db, prices)

        # Bayesian weight update
        await run_bayesian_learning(db)

        # Update symbol profiles
        await update_symbol_profiles(db)

        # Save daily performance
        await save_daily_performance(db)

    logger.info("✅ Learning cycle complete")


async def seed_default_data():
    """Create default admin user, symbols, and news sources if they don't exist."""
    async with AsyncSessionLocal() as db:
        # Check if admin exists
        result = await db.execute(select(User).where(User.role == "admin"))
        if not result.scalar_one_or_none():
            admin = User(
                username="admin",
                email="admin@cryptoanalyzer.local",
                password_hash=hash_password("admin123"),
                role="admin",
            )
            db.add(admin)
            await db.flush()

            # Default bot settings for admin
            db.add(BotSettings(user_id=admin.id))
            db.add(UserNotificationPreference(user_id=admin.id))
            await db.flush()

            logger.info("✅ Default admin created: admin@cryptoanalyzer.local / admin123")

        # Seed default trusted news sources (only)
        default_sources = [
            ("CoinDesk", "https://coindesk.com"),
            ("Reuters", "https://reuters.com"),
            ("Bloomberg", "https://bloomberg.com"),
            ("The Block", "https://theblock.co"),
            ("Decrypt", "https://decrypt.co"),
            ("CoinTelegraph", "https://cointelegraph.com"),
        ]
        for name, url in default_sources:
            existing = await db.execute(
                select(TrustedNewsSource).where(TrustedNewsSource.name == name)
            )
            if not existing.scalar_one_or_none():
                db.add(TrustedNewsSource(name=name, url=url, is_suggested=True))

        await db.commit()
        logger.info("✅ Default data seeded")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    # Startup
    logger.info("🚀 Starting CryptoAnalyzer...")
    await init_db()

    # Migrate: add missing columns to paper_bot_settings and bot_settings
    from sqlalchemy import text
    async with engine.begin() as conn:
        for table_name in ["paper_bot_settings", "bot_settings"]:
            try:
                result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
                columns = [row[1] for row in result.fetchall()]
            except Exception:
                continue
            for col_name, col_type in [
                ("max_daily_loss", "NUMERIC DEFAULT 200"),
                ("min_loss_limit", "NUMERIC DEFAULT 10"),
                ("max_loss_limit", "NUMERIC DEFAULT 500"),
                ("min_confidence", "NUMERIC DEFAULT 40"),
                ("signal_duration_multiplier", "NUMERIC DEFAULT 1.0"),
                ("trade_size_pct", "NUMERIC DEFAULT 20"),
                ("max_open_positions", "INTEGER DEFAULT 5"),
            ]:
                if col_name not in columns:
                    try:
                        await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
                        logger.info(f"✅ Added column {col_name} to {table_name}")
                    except Exception:
                        pass

        # Migrate paper_holdings
        try:
            result = await conn.execute(text("PRAGMA table_info(paper_holdings)"))
            columns = [row[1] for row in result.fetchall()]
            for col_name, col_type in [
                ("take_profit_price", "NUMERIC"),
                ("stop_loss_price", "NUMERIC"),
                ("signal_id", "VARCHAR(36)"),
                ("entry_trade_id", "VARCHAR(36)"),
            ]:
                if col_name not in columns:
                    try:
                        await conn.execute(text(f"ALTER TABLE paper_holdings ADD COLUMN {col_name} {col_type}"))
                        logger.info(f"✅ Added column {col_name} to paper_holdings")
                    except Exception:
                        pass
        except Exception:
            pass

        # Migrate trade_signals
        try:
            result = await conn.execute(text("PRAGMA table_info(trade_signals)"))
            columns = [row[1] for row in result.fetchall()]
            for col_name, col_type in [
                ("close_price", "NUMERIC"),
                ("pnl_percentage", "NUMERIC"),
            ]:
                if col_name not in columns:
                    try:
                        await conn.execute(text(f"ALTER TABLE trade_signals ADD COLUMN {col_name} {col_type}"))
                        logger.info(f"✅ Added column {col_name} to trade_signals")
                    except Exception:
                        pass
        except Exception:
            pass

    await seed_default_data()

    # Seed component weights for learning
    from app.services.statistical_learner import seed_weights
    async with AsyncSessionLocal() as db:
        await seed_weights(db)

    # Start Binance WebSocket for live prices (avoids REST API rate limits)
    from app.services.binance_client import start_price_stream
    async with AsyncSessionLocal() as db:
        sym_result = await db.execute(
            select(SupportedSymbol).where(SupportedSymbol.is_active == True)
        )
        active_symbols = [s.symbol for s in sym_result.scalars().all()]
    if active_symbols:
        import asyncio as aio
        aio.create_task(start_price_stream(active_symbols))
        logger.info(f"🔌 WebSocket price stream started for {len(active_symbols)} symbols")

    # Start scheduler
    scheduler.add_job(run_analysis_job, "interval", minutes=15, id="analysis_job")
    scheduler.add_job(run_price_monitor_job, "interval", seconds=5, id="price_monitor_job")
    scheduler.add_job(run_paper_bot_job, "interval", minutes=1, id="paper_bot_job")
    scheduler.add_job(run_signals_job, "interval", minutes=5, id="signals_job")
    scheduler.add_job(run_learning_job, "interval", hours=4, id="learning_job")
    scheduler.start()
    logger.info("⏰ Deterministic analysis started (every 15 min)")
    logger.info("⏰ Paper bot scheduler started (every 1 min)")
    logger.info("⏰ Signal generator started (every 5 min)")
    logger.info("⏰ Price monitor started (every 5 sec)")
    logger.info("⏰ Learning cycle started (every 4 hours)")

    yield

    # Shutdown
    from app.services.binance_client import stop_price_stream
    await stop_price_stream()
    scheduler.shutdown()
    logger.info("👋 CryptoAnalyzer stopped")


# ===== Create App =====
app = FastAPI(
    title="CryptoAnalyzer API",
    description="منصة تحليل وتداول العملات الرقمية",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(wallets_router)
app.include_router(trades_router)
app.include_router(notifications_router)
app.include_router(market_router)
app.include_router(ws_router)
app.include_router(paper_router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "version": "2.0.0"}


@app.post("/api/admin/run-analysis")
async def trigger_analysis(admin: User = Depends(require_admin)):
    """Manually trigger analysis (admin only — async, returns immediately)."""
    import asyncio
    asyncio.create_task(run_analysis_job())
    return {"message": "تم بدء التحليل"}


@app.post("/api/admin/run-analysis-sync")
async def trigger_analysis_sync(admin: User = Depends(require_admin)):
    """Manually trigger analysis and WAIT for completion (admin only)."""
    await run_analysis_job()
    return {"message": "✅ تم التحليل بنجاح"}
