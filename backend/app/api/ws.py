"""
CryptoAnalyzer — WebSocket endpoints for live data
"""

import json
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set
import httpx

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.services.binance_client import get_prices_batch
from sqlalchemy import select
from app.models.trade import SupportedSymbol
from app.models.analysis import BotAnalysis

router = APIRouter(tags=["WebSocket"])
settings = get_settings()
logger = logging.getLogger(__name__)

# Connected clients
live_clients: Set[WebSocket] = set()


@router.websocket("/ws/live-analysis")
async def live_analysis(ws: WebSocket):
    """
    WebSocket: streams live prices + latest analysis for active symbols.
    Sends updates every 5 seconds.
    """
    await ws.accept()
    live_clients.add(ws)
    logger.info(f"WebSocket client connected. Total: {len(live_clients)}")

    try:
        while True:
            try:
                data = await build_live_data()
                await ws.send_json(data)
            except Exception as e:
                logger.error(f"Error building live data: {e}")
                await ws.send_json({"error": str(e)})

            await asyncio.sleep(5)
    except WebSocketDisconnect:
        live_clients.discard(ws)
        logger.info(f"WebSocket client disconnected. Total: {len(live_clients)}")
    except Exception:
        live_clients.discard(ws)


async def build_live_data() -> dict:
    """Build live data payload with prices and latest analyses."""
    async with AsyncSessionLocal() as db:
        # Get active symbols
        result = await db.execute(
            select(SupportedSymbol).where(SupportedSymbol.is_active == True)
        )
        symbols = result.scalars().all()
        symbol_names = [s.symbol for s in symbols]

        # Get live prices from Binance
        prices = {}
        if symbol_names:
            try:
                prices = await get_prices_batch(symbol_names)
            except Exception:
                pass

        # Get 24h tickers for change %
        tickers_24h = {}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{settings.BINANCE_BASE_URL}/api/v3/ticker/24hr",
                    timeout=10,
                )
                if resp.status_code == 200:
                    for t in resp.json():
                        if t["symbol"] in symbol_names:
                            tickers_24h[t["symbol"]] = {
                                "change_pct": float(t.get("priceChangePercent", 0)),
                                "volume": float(t.get("volume", 0)),
                                "high": float(t.get("highPrice", 0)),
                                "low": float(t.get("lowPrice", 0)),
                            }
        except Exception:
            pass

        # Get latest analysis for each symbol
        from sqlalchemy import desc
        analyses = {}
        for sym_name in symbol_names:
            result = await db.execute(
                select(BotAnalysis)
                .where(BotAnalysis.symbol == sym_name)
                .order_by(desc(BotAnalysis.created_at))
                .limit(1)
            )
            analysis = result.scalar_one_or_none()
            if analysis:
                analyses[sym_name] = {
                    "decision": analysis.decision,
                    "confidence": float(analysis.confidence_score or 0),
                    "reasoning": analysis.reasoning,
                    "technical_indicators": analysis.technical_indicators,
                    "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
                }

        # Build response
        coins = []
        for sym in symbols:
            price = prices.get(sym.symbol, 0)
            ticker = tickers_24h.get(sym.symbol, {})
            analysis = analyses.get(sym.symbol)

            coins.append({
                "symbol": sym.symbol,
                "base_asset": sym.base_asset,
                "price": price,
                "change_24h": ticker.get("change_pct", 0),
                "volume_24h": ticker.get("volume", 0),
                "high_24h": ticker.get("high", 0),
                "low_24h": ticker.get("low", 0),
                "analysis": analysis,
            })

        return {
            "type": "live_update",
            "timestamp": asyncio.get_event_loop().time(),
            "coins": coins,
        }


async def broadcast_trade_event(event: dict):
    """Broadcast trade execution events to all connected WebSocket clients."""
    disconnected = set()
    for ws in live_clients:
        try:
            await ws.send_json({"type": "trade_event", **event})
        except Exception:
            disconnected.add(ws)
    live_clients.difference_update(disconnected)
