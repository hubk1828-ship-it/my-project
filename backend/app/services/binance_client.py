import hashlib
import hmac
import time
from typing import Optional, Dict, List
import httpx
from app.core.config import get_settings

settings = get_settings()


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
        return {"X-MBX-APIKEY": self.api_key}

    async def get_account(self) -> dict:
        """Get account info and balances."""
        params = self._sign({})
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/v3/account",
                params=params,
                headers=self._headers(),
                timeout=10,
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
            resp = await client.post(
                f"{self.base_url}/api/v3/order",
                params=params,
                headers=self._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_ticker_price(self, symbol: str) -> float:
        """Get current price for a symbol."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/v3/ticker/price",
                params={"symbol": symbol},
                timeout=10,
            )
            resp.raise_for_status()
            return float(resp.json()["price"])

    async def get_klines(
        self, symbol: str, interval: str = "4h", limit: int = 50
    ) -> List[list]:
        """Get candlestick data."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/v3/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_24h_ticker(self, symbol: str) -> dict:
        """Get 24h rolling ticker."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/v3/ticker/24hr",
                params={"symbol": symbol},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()


async def get_prices_batch(symbols: List[str]) -> Dict[str, float]:
    """Get prices for multiple symbols without auth."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.BINANCE_BASE_URL}/api/v3/ticker/price",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            item["symbol"]: float(item["price"])
            for item in data
            if item["symbol"] in symbols
        }


async def verify_api_key(api_key: str, api_secret: str) -> bool:
    """Test if API key is valid by fetching account info."""
    try:
        client = BinanceClient(api_key, api_secret)
        await client.get_account()
        return True
    except Exception:
        return False
