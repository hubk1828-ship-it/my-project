"""
CryptoAnalyzer — Analysis Engine
Core analysis logic with 4-step decision process + Smart Money Concepts (SMC).
"""

import logging
from typing import Optional, Dict, List
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import httpx
from app.core.config import get_settings
from app.services.binance_client import get_prices_batch, _request_with_retry, BINANCE_HEADERS
from app.services.smc_engine import SMCEngine

settings = get_settings()
logger = logging.getLogger(__name__)
smc = SMCEngine(swing_length=50, internal_length=5, eqhl_length=3)

TRUSTED_SOURCES = ["CoinDesk", "Reuters", "Bloomberg", "The Block", "Decrypt", "CoinTelegraph"]


# ===== Step 1: Check if Momentum is Real =====

async def check_momentum(symbol: str) -> Dict:
    """
    Compare current volume to 7-day average.
    Real momentum: volume > 150% of avg.
    """
    try:
        async with httpx.AsyncClient() as client:
            # Get 7 days of 1h klines (168 candles)
            resp = await _request_with_retry(
                client, "get", f"{settings.BINANCE_BASE_URL}/api/v3/klines",
                params={"symbol": symbol, "interval": "1h", "limit": 168},
                timeout=15,
            )
            resp.raise_for_status()
            klines = resp.json()

        if len(klines) < 24:
            return {"is_real": None, "ratio": 0, "reason": "بيانات غير كافية"}

        # Volume is index 5 in kline data
        volumes = [float(k[5]) for k in klines]
        avg_volume_7d = np.mean(volumes[:-24]) if len(volumes) > 24 else np.mean(volumes)
        current_avg_volume = np.mean(volumes[-24:])  # Last 24h avg

        ratio = current_avg_volume / avg_volume_7d if avg_volume_7d > 0 else 0

        is_real = ratio >= 1.5

        return {
            "is_real": is_real,
            "ratio": round(ratio, 2),
            "reason": f"حجم التداول {'أعلى' if is_real else 'أقل'} من المتوسط بنسبة {round(ratio * 100)}%"
        }
    except Exception as e:
        logger.error(f"Momentum check failed for {symbol}: {e}")
        return {"is_real": None, "ratio": 0, "reason": f"خطأ في جلب البيانات: {str(e)}"}


# ===== Step 2: Price Confirms News? =====

async def check_price_confirms_news(
    symbol: str,
    news_sentiment: Optional[str],  # positive | negative | neutral
    news_timestamp: Optional[datetime],
) -> Dict:
    """
    Check if price moved in same direction as news by > 1.5%.
    """
    if not news_sentiment or not news_timestamp:
        return {"confirmed": None, "change_pct": 0, "reason": "لا يوجد خبر مؤثر للمقارنة"}

    try:
        # Get klines around news time
        start_time = int((news_timestamp - timedelta(hours=1)).timestamp() * 1000)
        end_time = int((news_timestamp + timedelta(hours=2)).timestamp() * 1000)

        async with httpx.AsyncClient() as client:
            resp = await _request_with_retry(
                client, "get", f"{settings.BINANCE_BASE_URL}/api/v3/klines",
                params={
                    "symbol": symbol,
                    "interval": "15m",
                    "startTime": start_time,
                    "endTime": end_time,
                },
                timeout=15,
            )
            resp.raise_for_status()
            klines = resp.json()

        if len(klines) < 4:
            return {"confirmed": None, "change_pct": 0, "reason": "بيانات غير كافية حول وقت الخبر"}

        price_before = float(klines[0][1])  # Open of first candle
        price_after = float(klines[-1][4])  # Close of last candle
        change_pct = ((price_after - price_before) / price_before) * 100

        if news_sentiment == "positive":
            confirmed = change_pct >= 1.5
        elif news_sentiment == "negative":
            confirmed = change_pct <= -1.5
        else:
            confirmed = None

        return {
            "confirmed": confirmed,
            "change_pct": round(change_pct, 2),
            "reason": f"{'السعر أكّد الخبر' if confirmed else 'السعر لم يؤكّد الخبر'} — تغيّر {round(change_pct, 2)}%"
        }
    except Exception as e:
        logger.error(f"Price confirmation check failed for {symbol}: {e}")
        return {"confirmed": None, "change_pct": 0, "reason": f"خطأ: {str(e)}"}


# ===== Step 3: Technical Analysis + SMC =====

async def analyze_chart(symbol: str, timeframe: str = "1h") -> Dict:
    """
    Fetch klines for given timeframe and compute RSI, EMA, support/resistance + SMC.
    Valid timeframes: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await _request_with_retry(
                client, "get", f"{settings.BINANCE_BASE_URL}/api/v3/klines",
                params={"symbol": symbol, "interval": timeframe, "limit": 200},
                timeout=15,
            )
            resp.raise_for_status()
            klines = resp.json()

        df = pd.DataFrame(klines, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "trades", "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        df["open"] = df["open"].astype(float)
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["volume"] = df["volume"].astype(float)

        closes = df["close"].values
        opens = df["open"].values
        highs_arr = df["high"].values
        lows_arr = df["low"].values
        vols = df["volume"].values

        # RSI (14 periods)
        deltas = np.diff(closes)
        gain = np.where(deltas > 0, deltas, 0)
        loss = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gain[-14:])
        avg_loss = np.mean(loss[-14:])
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = 100 - (100 / (1 + rs))

        # EMA 20 & 50
        ema20 = pd.Series(closes).ewm(span=20).mean().iloc[-1]
        ema50 = pd.Series(closes).ewm(span=50).mean().iloc[-1]

        # Support & Resistance (simple: recent lows/highs)
        recent_lows = df["low"].tail(20)
        recent_highs = df["high"].tail(20)
        support = float(recent_lows.min())
        resistance = float(recent_highs.max())

        current_price = closes[-1]

        # Determine trend
        if ema20 > ema50 and rsi < 70:
            trend = "صاعد"
        elif ema20 < ema50 and rsi > 30:
            trend = "هابط"
        else:
            trend = "عرضي"

        # ===== SMC Analysis =====
        smc_result = smc.analyze(
            opens=opens.tolist(),
            highs=highs_arr.tolist(),
            lows=lows_arr.tolist(),
            closes=closes.tolist(),
            volumes=vols.tolist(),
        )
        smc_signal = smc_result.get_signal()
        smc_data = smc_result.to_dict()

        return {
            "trend": trend,
            "rsi": round(float(rsi), 2),
            "ema20": round(float(ema20), 2),
            "ema50": round(float(ema50), 2),
            "support": round(support, 2),
            "resistance": round(resistance, 2),
            "current_price": round(current_price, 2),
            "reason": f"الاتجاه {trend} — RSI: {round(rsi, 1)}, EMA20 {'>' if ema20 > ema50 else '<'} EMA50",
            "smc": smc_data,
            "smc_signal": smc_signal,
        }
    except Exception as e:
        logger.error(f"Chart analysis failed for {symbol}: {e}")
        return {
            "trend": "غير محدد",
            "rsi": 0, "ema20": 0, "ema50": 0,
            "support": 0, "resistance": 0, "current_price": 0,
            "reason": f"خطأ في التحليل الفني: {str(e)}",
            "smc": None, "smc_signal": None,
        }


# ===== Step 4: Final Decision (Classic + SMC) =====

def make_decision(
    momentum: Dict,
    price_confirmation: Dict,
    chart: Dict,
) -> Dict:
    """
    Final decision: combines classic TA (40%) + SMC signals (60%).
    """
    classic_score = 0
    reasons = []

    # --- Classic TA scoring (max 40) ---
    # Momentum (15 pts)
    if momentum["is_real"] is True:
        classic_score += 15
        reasons.append(f"✅ زخم حقيقي ({momentum['reason']})")
    elif momentum["is_real"] is False:
        reasons.append(f"❌ زخم ضعيف ({momentum['reason']})")
    else:
        reasons.append(f"⚠️ {momentum['reason']}")

    # Price confirmation (10 pts)
    if price_confirmation["confirmed"] is True:
        classic_score += 10
        reasons.append(f"✅ السعر أكّد الخبر ({price_confirmation['reason']})")
    elif price_confirmation["confirmed"] is False:
        reasons.append(f"❌ {price_confirmation['reason']}")
    else:
        reasons.append(f"⚠️ {price_confirmation['reason']}")

    # TA trend (15 pts)
    rsi = chart.get("rsi", 50)
    if chart["trend"] == "صاعد":
        classic_score += 10
        if 30 < rsi < 70:
            classic_score += 5
        reasons.append(f"✅ اتجاه صاعد ({chart['reason']})")
    elif chart["trend"] == "هابط":
        classic_score += 10
        if 30 < rsi < 70:
            classic_score += 5
        reasons.append(f"✅ اتجاه هابط ({chart['reason']})")
    else:
        reasons.append(f"⚠️ اتجاه عرضي — لا وضوح ({chart['reason']})")

    # --- SMC scoring (max 60) ---
    smc_signal = chart.get("smc_signal")
    smc_score = 0
    smc_decision = None

    if smc_signal:
        # SMC confidence is 0-100, scale to 0-60
        smc_score = int(smc_signal["confidence"] * 0.6)
        smc_decision = smc_signal["decision"]
        reasons.append("")
        reasons.append("━━━ Smart Money Concepts ━━━")
        for sig in smc_signal.get("signals", []):
            reasons.append(sig)

    # --- Combined score ---
    confidence = classic_score + smc_score

    # --- Decision logic ---
    # SMC has priority if it gives a clear signal
    if smc_decision in ("buy", "sell") and smc_signal and smc_signal["confidence"] >= 60:
        decision = smc_decision
    elif (
        momentum["is_real"] is True
        and price_confirmation["confirmed"] is True
        and chart["trend"] == "صاعد"
    ):
        decision = "buy"
    elif (
        momentum["is_real"] is True
        and price_confirmation["confirmed"] is True
        and chart["trend"] == "هابط"
    ):
        decision = "sell"
    else:
        decision = smc_decision if smc_decision else "no_opportunity"
        if decision == "no_opportunity" and confidence > 60:
            confidence = 55

    return {
        "decision": decision,
        "confidence_score": min(confidence, 100),
        "reasoning": "\n".join(reasons),
    }


# ===== News Fetching =====

async def fetch_news(symbol_base: str) -> Optional[Dict]:
    """Fetch news from CryptoPanic API, filtered by trusted sources."""
    if not settings.CRYPTOPANIC_API_KEY:
        return None

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.CRYPTOPANIC_BASE_URL}/posts/",
                params={
                    "auth_token": settings.CRYPTOPANIC_API_KEY,
                    "currencies": symbol_base,
                    "filter": "important",
                    "public": "true",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        for article in results:
            source = article.get("source", {}).get("title", "")
            if source in TRUSTED_SOURCES:
                # Determine sentiment from votes
                votes = article.get("votes", {})
                positive = votes.get("positive", 0)
                negative = votes.get("negative", 0)

                if positive > negative:
                    sentiment = "positive"
                elif negative > positive:
                    sentiment = "negative"
                else:
                    sentiment = "neutral"

                return {
                    "source": source,
                    "title": article.get("title", ""),
                    "url": article.get("url", ""),
                    "sentiment": sentiment,
                    "published_at": datetime.fromisoformat(
                        article["published_at"].replace("Z", "+00:00")
                    ) if article.get("published_at") else None,
                }

        return None
    except Exception as e:
        logger.error(f"News fetch failed for {symbol_base}: {e}")
        return None


# ===== Full Analysis Pipeline =====

async def analyze_symbol(symbol: str, base_asset: str, timeframe: str = "1h") -> Dict:
    """Run full 4-step analysis for a single symbol."""
    logger.info(f"Analyzing {symbol} on {timeframe}...")

    # Fetch news
    news = await fetch_news(base_asset)

    # Step 1: Momentum
    momentum = await check_momentum(symbol)

    # Step 2: Price confirms news
    price_confirmation = await check_price_confirms_news(
        symbol,
        news["sentiment"] if news else None,
        news["published_at"] if news else None,
    )

    # Step 3: Chart analysis
    chart = await analyze_chart(symbol, timeframe)

    # Step 4: Decision
    decision_result = make_decision(momentum, price_confirmation, chart)

    return {
        "symbol": symbol,
        "news_source": news["source"] if news else None,
        "news_title": news["title"] if news else None,
        "news_url": news["url"] if news else None,
        "is_momentum_real": momentum["is_real"],
        "price_confirmed_news": price_confirmation["confirmed"],
        "decision": decision_result["decision"],
        "confidence_score": decision_result["confidence_score"],
        "reasoning": decision_result["reasoning"],
        "technical_indicators": {
            "rsi": chart.get("rsi"),
            "ema20": chart.get("ema20"),
            "ema50": chart.get("ema50"),
            "support": chart.get("support"),
            "resistance": chart.get("resistance"),
            "trend": chart.get("trend"),
            "volume_ratio": momentum.get("ratio"),
            "price_change_pct": price_confirmation.get("change_pct"),
            "current_price": chart.get("current_price"),
            "smc": chart.get("smc"),
        },
    }
