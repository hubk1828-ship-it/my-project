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
    """Scheduled job: run Confluence AI analysis for all active symbols."""
    from app.services.confluence_analyzer import analyze_symbol_confluence
    from app.services.analyzer import analyze_symbol  # Fallback
    from app.services.notifier import send_notification, format_opportunity_alert
    from app.services.binance_client import get_prices_batch

    logger.info("🧠 Starting Confluence AI analysis...")

    async with AsyncSessionLocal() as db:
        # Get active symbols
        result = await db.execute(
            select(SupportedSymbol).where(SupportedSymbol.is_active == True)
        )
        symbols = result.scalars().all()

        for i, sym in enumerate(symbols):
            try:
                # Delay between symbols to avoid Binance rate limits
                if i > 0:
                    import asyncio
                    await asyncio.sleep(3)

                # Try Confluence AI first, fallback to classic
                try:
                    analysis_result = await analyze_symbol_confluence(sym.symbol, sym.base_asset)
                except Exception as e:
                    logger.warning(f"Confluence failed for {sym.symbol}: {e}, using classic")
                    analysis_result = await analyze_symbol(sym.symbol, sym.base_asset)

                # Save to DB
                analysis = BotAnalysis(**analysis_result)
                db.add(analysis)
                await db.flush()

                # If opportunity found, notify users and execute auto-trades
                if analysis.decision in ("buy", "sell"):
                    prices = await get_prices_batch([sym.symbol])
                    price = prices.get(sym.symbol, 0)

                    # Notify all active users
                    users_result = await db.execute(
                        select(User).where(User.is_active == True)
                    )
                    for user in users_result.scalars().all():
                        content = format_opportunity_alert(
                            sym.symbol, analysis.decision, price, analysis.reasoning
                        )
                        await send_notification(user.id, "opportunity", content, db)

                    # Auto-trade for enabled users — direct link between analysis and trading
                    from app.services.trader import check_trade_limits, execute_auto_trade
                    from app.services.notifier import format_trade_executed_alert, format_trade_failed_alert
                    from app.api.ws import broadcast_trade_event

                    settings_result = await db.execute(
                        select(BotSettings).where(
                            BotSettings.is_auto_trade_enabled == True,
                            BotSettings.is_admin_approved == True,
                        )
                    )
                    for bot_setting in settings_result.scalars().all():
                        # Get user wallet
                        wallet_result = await db.execute(
                            select(Wallet).where(
                                Wallet.user_id == bot_setting.user_id,
                                Wallet.is_active == True,
                            )
                        )
                        wallet = wallet_result.scalar_one_or_none()
                        if not wallet:
                            continue

                        trade_amount = float(bot_setting.max_trade_amount)
                        limits_check = await check_trade_limits(
                            bot_setting.user_id, bot_setting, trade_amount, trade_amount * 10, db
                        )

                        if limits_check["can_trade"]:
                            result = await execute_auto_trade(
                                bot_setting.user_id, wallet, analysis, trade_amount, db
                            )

                            # Broadcast trade event via WebSocket
                            await broadcast_trade_event({
                                "symbol": sym.symbol,
                                "side": analysis.decision,
                                "success": result["success"],
                                "price": result.get("price", 0),
                                "quantity": result.get("quantity", 0),
                                "total_value": result.get("total_value", 0),
                            })

                            if result["success"]:
                                content = format_trade_executed_alert(
                                    sym.symbol, analysis.decision,
                                    result["quantity"], result["price"], result["total_value"]
                                )
                                await send_notification(bot_setting.user_id, "trade_executed", content, db)
                            else:
                                content = format_trade_failed_alert(sym.symbol, result["error"])
                                await send_notification(bot_setting.user_id, "trade_failed", content, db)

                logger.info(f"✅ {sym.symbol}: {analysis_result['decision']}")
            except Exception as e:
                logger.error(f"❌ Analysis failed for {sym.symbol}: {e}")

        await db.commit()

    logger.info("✅ Analysis cycle complete")


async def run_paper_bot_job():
    """Scheduled job: run paper trading bot for all enabled users."""
    from app.services.paper_trader import run_paper_bot_cycle
    logger.info("📄 Starting paper bot cycle...")
    async with AsyncSessionLocal() as db:
        await run_paper_bot_cycle(db)


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

        # Seed default symbols
        default_symbols = [
            ("BTCUSDT", "BTC", True), ("ETHUSDT", "ETH", True),
            ("BNBUSDT", "BNB", False), ("SOLUSDT", "SOL", False),
            ("XRPUSDT", "XRP", False), ("ADAUSDT", "ADA", False),
            ("DOGEUSDT", "DOGE", False), ("AVAXUSDT", "AVAX", False),
        ]
        for symbol, base, is_default in default_symbols:
            existing = await db.execute(
                select(SupportedSymbol).where(SupportedSymbol.symbol == symbol)
            )
            if not existing.scalar_one_or_none():
                db.add(SupportedSymbol(symbol=symbol, base_asset=base, is_default=is_default))

        # Seed default trusted news sources
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

        # Seed demo analysis data
        from datetime import datetime, timezone
        existing_analysis = await db.execute(select(BotAnalysis).limit(1))
        if not existing_analysis.scalar_one_or_none():
            demo_analyses = [
                BotAnalysis(
                    symbol="BTCUSDT", timeframe="1h",
                    news_source="Reuters", news_title="Bitcoin ETF inflows reach new weekly high",
                    news_url="https://reuters.com/example",
                    is_momentum_real=True, price_confirmed_news=True,
                    decision="buy", confidence_score=85,
                    reasoning="✅ زخم حقيقي (حجم التداول أعلى من المتوسط بنسبة 180%)\n✅ السعر أكّد الخبر (تغيّر +2.3%)\n✅ اتجاه صاعد (RSI: 58, EMA20 > EMA50)",
                    technical_indicators={"rsi": 58.2, "ema20": 67432.5, "ema50": 65210.8, "support": 63500, "resistance": 69800, "trend": "صاعد", "volume_ratio": 1.8, "price_change_pct": 2.3, "current_price": 67432.50},
                    created_at=datetime.now(timezone.utc),
                ),
                BotAnalysis(
                    symbol="ETHUSDT", timeframe="1h",
                    news_source="CoinDesk", news_title="Ethereum network upgrade scheduled for next month",
                    news_url="https://coindesk.com/example",
                    is_momentum_real=True, price_confirmed_news=True,
                    decision="sell", confidence_score=72,
                    reasoning="✅ زخم حقيقي (حجم التداول أعلى من المتوسط بنسبة 165%)\n✅ السعر أكّد الخبر (تغيّر -1.8%)\n✅ اتجاه هابط (RSI: 35, EMA20 < EMA50)",
                    technical_indicators={"rsi": 35.1, "ema20": 3380.2, "ema50": 3520.6, "support": 3200, "resistance": 3650, "trend": "هابط", "volume_ratio": 1.65, "price_change_pct": -1.8, "current_price": 3421.80},
                    created_at=datetime.now(timezone.utc),
                ),
                BotAnalysis(
                    symbol="SOLUSDT", timeframe="1h",
                    news_source=None, news_title=None, news_url=None,
                    is_momentum_real=False, price_confirmed_news=None,
                    decision="no_opportunity", confidence_score=25,
                    reasoning="❌ زخم ضعيف (حجم التداول أقل من المتوسط بنسبة 85%)\n⚠️ لا يوجد خبر مؤثر للمقارنة\n⚠️ اتجاه عرضي — لا وضوح (RSI: 48, EMA20 ≈ EMA50)",
                    technical_indicators={"rsi": 48.5, "ema20": 142.3, "ema50": 143.1, "support": 130, "resistance": 155, "trend": "عرضي", "volume_ratio": 0.85, "price_change_pct": 0, "current_price": 142.65},
                    created_at=datetime.now(timezone.utc),
                ),
                BotAnalysis(
                    symbol="BNBUSDT", timeframe="1h",
                    news_source=None, news_title=None, news_url=None,
                    is_momentum_real=False, price_confirmed_news=None,
                    decision="no_opportunity", confidence_score=40,
                    reasoning="❌ زخم ضعيف (حجم التداول أقل من المتوسط بنسبة 110%)\n⚠️ لا يوجد خبر مؤثر للمقارنة\n⚠️ اتجاه عرضي — لا وضوح (RSI: 52, EMA20 ≈ EMA50)",
                    technical_indicators={"rsi": 52.0, "ema20": 582.4, "ema50": 585.1, "support": 560, "resistance": 610, "trend": "عرضي", "volume_ratio": 1.1, "price_change_pct": 0, "current_price": 583.20},
                    created_at=datetime.now(timezone.utc),
                ),
                BotAnalysis(
                    symbol="XRPUSDT", timeframe="1h",
                    news_source=None, news_title=None, news_url=None,
                    is_momentum_real=False, price_confirmed_news=None,
                    decision="no_opportunity", confidence_score=20,
                    reasoning="❌ زخم ضعيف (حجم التداول أقل من المتوسط بنسبة 72%)\n⚠️ لا يوجد خبر مؤثر للمقارنة\n⚠️ اتجاه عرضي — لا وضوح (RSI: 46, EMA20 ≈ EMA50)",
                    technical_indicators={"rsi": 46.0, "ema20": 0.52, "ema50": 0.53, "support": 0.48, "resistance": 0.58, "trend": "عرضي", "volume_ratio": 0.72, "price_change_pct": 0, "current_price": 0.52},
                    created_at=datetime.now(timezone.utc),
                ),
            ]
            for a in demo_analyses:
                db.add(a)
            logger.info("✅ Demo analysis data seeded")

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
            ]:
                if col_name not in columns:
                    try:
                        await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
                        logger.info(f"✅ Added column {col_name} to {table_name}")
                    except Exception:
                        pass

    await seed_default_data()

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
    scheduler.add_job(run_analysis_job, "interval", hours=1, id="analysis_job")
    scheduler.add_job(run_paper_bot_job, "interval", hours=1, id="paper_bot_job", minutes=5)
    scheduler.add_job(run_signals_job, "interval", hours=2, id="signals_job")
    scheduler.start()
    logger.info("⏰ Analysis scheduler started (every 1 hour)")
    logger.info("⏰ Paper bot scheduler started (every 1 hour)")
    logger.info("⏰ Signal generator started (every 2 hours)")

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
    """Manually trigger analysis (admin only — protected)."""
    import asyncio
    asyncio.create_task(run_analysis_job())
    return {"message": "تم بدء التحليل"}
