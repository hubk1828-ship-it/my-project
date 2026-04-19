import hashlib
import hmac
import time
import asyncio
from typing import Optional, Dict, List
import httpx
from app.core.config import get_settings

settings = get_settings()

# Shared headers to avoid WAF blocks
BINANCE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

# Simple price cache to reduce API calls
_price_cache: Dict[str, tuple] = {}  # symbol -> (price, timestamp)
CACHE_TTL = 30  # seconds


# Ban tracking — stops ALL REST requests if IP is banned
_ban_until: float = 0  # Unix timestamp when ban expires


async def _request_with_retry(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    """Make request — if IP is banned, skip entirely until ban expires."""
    global _ban_until

    # If we're currently banned, don't even try (avoids extending ban)
    now = time.time()
    if now < _ban_until:
        # Return a fake 418 response without hitting Binance
        return httpx.Response(418, text=f"IP banned until {_ban_until}")

    kwargs.setdefault("headers", {}).update(BINANCE_HEADERS)
    resp = await getattr(client, method)(url, **kwargs)

    if resp.status_code == 418:
        # Parse ban expiry from response
        try:
            ban_info = resp.json()
            ban_until_ms = ban_info.get("msg", "")
            # Extract timestamp from: "...IP banned until 1776622427103..."
            import re
            match = re.search(r"until\s+(\d+)", ban_until_ms)
            if match:
                _ban_until = int(match.group(1)) / 1000
            else:
                _ban_until = now + 300  # Default 5 min ban
        except Exception:
            _ban_until = now + 300
        import logging
        logging.getLogger("binance").warning(f"🚫 IP banned until {_ban_until} — skipping REST calls")

    elif resp.status_code == 429:
        # Rate limited — wait and retry once
        await asyncio.sleep(5)
        resp = await getattr(client, method)(url, **kwargs)

    return resp


class BinanceClient:
    """Binance API client for account data and order execution."""

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = settings.BINANCE_BASE_URL

    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    def _headers(self) -> dict:
        return {**BINANCE_HEADERS, "X-MBX-APIKEY": self.api_key}

    async def get_account(self) -> dict:
        """Get account info and balances."""
        params = self._sign({})
        async with httpx.AsyncClient() as client:
            resp = await _request_with_retry(
                client, "get", f"{self.base_url}/api/v3/account",
                params=params, headers=self._headers(), timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_balances(self) -> List[dict]:
        """Get non-zero balances."""
        account = await self.get_account()
        return [
            b for b in account.get("balances", [])
            if float(b["free"]) > 0 or float(b["locked"]) > 0
        ]

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str = "MARKET",
        quote_order_qty: Optional[float] = None,
        quantity: Optional[float] = None,
    ) -> dict:
        """Place an order on Binance."""
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type,
        }
        if quote_order_qty:
            params["quoteOrderQty"] = str(quote_order_qty)
        elif quantity:
            params["quantity"] = str(quantity)

        params = self._sign(params)
        async with httpx.AsyncClient() as client:
            resp = await _request_with_retry(
                client, "post", f"{self.base_url}/api/v3/order",
                params=params, headers=self._headers(), timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_ticker_price(self, symbol: str) -> float:
        """Get current price for a symbol (with cache)."""
        now = time.time()
        if symbol in _price_cache:
            price, ts = _price_cache[symbol]
            if now - ts < CACHE_TTL:
                return price

        async with httpx.AsyncClient() as client:
            resp = await _request_with_retry(
                client, "get", f"{self.base_url}/api/v3/ticker/price",
                params={"symbol": symbol}, timeout=10,
            )
            resp.raise_for_status()
            price = float(resp.json()["price"])
            _price_cache[symbol] = (price, now)
            return price

    async def get_klines(
        self, symbol: str, interval: str = "4h", limit: int = 50
    ) -> List[list]:
        """Get candlestick data."""
        async with httpx.AsyncClient() as client:
            resp = await _request_with_retry(
                client, "get", f"{self.base_url}/api/v3/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_24h_ticker(self, symbol: str) -> dict:
        """Get 24h rolling ticker."""
        async with httpx.AsyncClient() as client:
            resp = await _request_with_retry(
                client, "get", f"{self.base_url}/api/v3/ticker/24hr",
                params={"symbol": symbol}, timeout=10,
            )
            resp.raise_for_status()
            return resp.json()


async def get_prices_batch(symbols: List[str]) -> Dict[str, float]:
    """Get prices — uses WebSocket cache first, REST as fallback."""
    now = time.time()
    results = {}
    missing = []

    for sym in symbols:
        if sym in _price_cache:
            price, ts = _price_cache[sym]
            if now - ts < 120:  # WS prices are live, allow 2min cache
                results[sym] = price
                continue
        missing.append(sym)

    # Only call REST if we have missing symbols and WS isn't providing them
    if missing:
        try:
            async with httpx.AsyncClient() as client:
                resp = await _request_with_retry(
                    client, "get", f"{settings.BINANCE_BASE_URL}/api/v3/ticker/price",
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data:
                        s = item["symbol"]
                        p = float(item["price"])
                        _price_cache[s] = (p, now)
                        if s in symbols:
                            results[s] = p
        except Exception:
            pass  # Use whatever we have from cache

    return results


# ===== Binance WebSocket Price Stream =====

import websockets
import json
import logging

_ws_logger = logging.getLogger("binance_ws")
_ws_running = False


async def start_price_stream(symbols: List[str]):
    """Connect to Binance WebSocket and stream live prices into cache."""
    global _ws_running
    if _ws_running:
        return
    _ws_running = True

    # Build stream names: btcusdt@miniTicker, ethusdt@miniTicker, etc.
    streams = [f"{s.lower()}@miniTicker" for s in symbols]
    url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"

    _ws_logger.info(f"🔌 Connecting to Binance WebSocket ({len(symbols)} symbols)...")

    while _ws_running:
        try:
            async with websockets.connect(url, ping_interval=30, ping_timeout=10) as ws:
                _ws_logger.info("✅ Binance WebSocket connected — live prices active")
                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        payload = data.get("data", {})
                        symbol = payload.get("s")
                        price = payload.get("c")  # Close price
                        if symbol and price:
                            _price_cache[symbol] = (float(price), time.time())
                    except Exception:
                        pass
        except Exception as e:
            _ws_logger.warning(f"⚠️ WebSocket disconnected: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

    _ws_logger.info("🔌 WebSocket stream stopped")


async def stop_price_stream():
    """Stop the WebSocket price stream."""
    global _ws_running
    _ws_running = False


async def verify_api_key(api_key: str, api_secret: str) -> bool:
    """Test if API key is valid by fetching account info."""
    try:
        client = BinanceClient(api_key, api_secret)
        await client.get_account()
        return True
    except Exception:
        return False

