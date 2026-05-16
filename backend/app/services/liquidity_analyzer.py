"""
Liquidity & Derivatives Analyzer — Fetches funding rate, open interest,
long/short ratio, order book depth, and Fear & Greed index.
All data is used as FILTERS, not decision sources.
"""
import logging
import time
from typing import Dict, Optional
import httpx

logger = logging.getLogger(__name__)

_cache: Dict[str, tuple] = {}
CACHE_TTL = 120  # 2 minutes


async def _fetch(url: str, params: dict = None, cache_key: str = None) -> Optional[dict | list]:
    """Fetch with cache and error handling."""
    now = time.time()
    if cache_key and cache_key in _cache:
        data, ts = _cache[cache_key]
        if now - ts < CACHE_TTL:
            return data
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            })
            if resp.status_code == 200:
                data = resp.json()
                if cache_key:
                    _cache[cache_key] = (data, now)
                return data
    except Exception as e:
        logger.warning(f"Fetch failed {url}: {e}")
    return None


async def get_funding_rate(symbol: str) -> float:
    """Get latest funding rate from Binance Futures."""
    data = await _fetch(
        "https://fapi.binance.com/fapi/v1/fundingRate",
        params={"symbol": symbol, "limit": "1"},
        cache_key=f"funding_{symbol}",
    )
    if data and isinstance(data, list) and len(data) > 0:
        return float(data[-1].get("fundingRate", 0))
    return 0.0


async def get_open_interest(symbol: str) -> float:
    """Get open interest from Binance Futures."""
    data = await _fetch(
        "https://fapi.binance.com/fapi/v1/openInterest",
        params={"symbol": symbol},
        cache_key=f"oi_{symbol}",
    )
    if data and isinstance(data, dict):
        return float(data.get("openInterest", 0))
    return 0.0


async def get_long_short_ratio(symbol: str, period: str = "15m") -> float:
    """Get global long/short account ratio."""
    data = await _fetch(
        "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
        params={"symbol": symbol, "period": period, "limit": "1"},
        cache_key=f"ls_{symbol}_{period}",
    )
    if data and isinstance(data, list) and len(data) > 0:
        return float(data[0].get("longShortRatio", 1.0))
    return 1.0


async def get_order_book(symbol: str, limit: int = 50) -> Dict:
    """Get order book depth."""
    data = await _fetch(
        "https://fapi.binance.com/fapi/v1/depth",
        params={"symbol": symbol, "limit": str(limit)},
        cache_key=f"ob_{symbol}",
    )
    return data or {}


async def get_fear_greed() -> int:
    """Get Fear & Greed Index (0-100)."""
    data = await _fetch(
        "https://api.alternative.me/fng/?limit=1",
        cache_key="fng",
    )
    if data and isinstance(data, dict):
        fng_data = data.get("data", [])
        if fng_data:
            return int(fng_data[0].get("value", 50))
    return 50


async def get_spot_price(symbol: str) -> float:
    """Get spot price for basis calculation."""
    data = await _fetch(
        "https://api.binance.com/api/v3/ticker/price",
        params={"symbol": symbol},
        cache_key=f"spot_{symbol}",
    )
    if data and isinstance(data, dict):
        return float(data.get("price", 0))
    return 0.0


async def get_all_liquidity_data(symbol: str) -> Dict:
    """Fetch all liquidity/derivatives data for a symbol."""
    import asyncio
    funding, oi, ls, ob, fng, spot = await asyncio.gather(
        get_funding_rate(symbol),
        get_open_interest(symbol),
        get_long_short_ratio(symbol),
        get_order_book(symbol),
        get_fear_greed(),
        get_spot_price(symbol),
        return_exceptions=True,
    )
    return {
        "funding_rate": funding if isinstance(funding, float) else 0.0,
        "open_interest": oi if isinstance(oi, float) else 0.0,
        "ls_ratio": ls if isinstance(ls, float) else 1.0,
        "order_book": ob if isinstance(ob, dict) else {},
        "fear_greed": fng if isinstance(fng, int) else 50,
        "spot_price": spot if isinstance(spot, float) else 0.0,
    }
