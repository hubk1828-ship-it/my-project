"""
Confluence Analyzer — AI-Powered Analysis Engine
Uses Groq AI (primary) + Google Gemini AI (fallback) with real Binance data for 6-layer analysis.
"""

import json
import re
import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.services.binance_client import (
    _request_with_retry, BINANCE_HEADERS, _price_cache, get_prices_batch
)

settings = get_settings()
logger = logging.getLogger("confluence")

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Gemini daily usage tracking
_daily_gemini_calls = 0
_gemini_day = None


def _track_gemini_call():
    global _daily_gemini_calls, _gemini_day
    today = datetime.now(timezone.utc).date()
    if _gemini_day != today:
        _daily_gemini_calls = 0
        _gemini_day = today
    _daily_gemini_calls += 1


# ===== Data Collection =====

async def get_klines_data(symbol: str, interval: str, limit: int = 50) -> List[Dict]:
    """Get kline data as structured dicts."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await _request_with_retry(
                client, "get", f"{settings.BINANCE_BASE_URL}/api/v3/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
                timeout=15,
            )
            if resp.status_code != 200:
                return []
            raw = resp.json()
            return [
                {
                    "time": k[0], "open": float(k[1]), "high": float(k[2]),
                    "low": float(k[3]), "close": float(k[4]), "volume": float(k[5]),
                }
                for k in raw
            ]
    except Exception as e:
        logger.warning(f"Klines failed {symbol}/{interval}: {e}")
        return []


async def get_ticker_24h(symbol: str) -> Dict:
    """Get 24h ticker data."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await _request_with_retry(
                client, "get", f"{settings.BINANCE_BASE_URL}/api/v3/ticker/24hr",
                params={"symbol": symbol}, timeout=10,
            )
            if resp.status_code == 200:
                d = resp.json()
                return {
                    "price": float(d["lastPrice"]),
                    "change_pct": float(d["priceChangePercent"]),
                    "volume_24h": float(d["quoteVolume"]),
                    "high_24h": float(d["highPrice"]),
                    "low_24h": float(d["lowPrice"]),
                }
    except Exception:
        pass
    return {}


async def get_funding_rate(symbol: str) -> Optional[float]:
    """Get current funding rate from Binance Futures."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await _request_with_retry(
                client, "get", f"{settings.BINANCE_FUTURES_URL}/fapi/v1/fundingRate",
                params={"symbol": symbol, "limit": 1}, timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    return float(data[0]["fundingRate"])
    except Exception:
        pass
    return None


async def get_open_interest(symbol: str) -> Optional[Dict]:
    """Get open interest from Binance Futures."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await _request_with_retry(
                client, "get", f"{settings.BINANCE_FUTURES_URL}/fapi/v1/openInterest",
                params={"symbol": symbol}, timeout=10,
            )
            if resp.status_code == 200:
                d = resp.json()
                return {"oi": float(d["openInterest"]), "symbol": d["symbol"]}
    except Exception:
        pass
    return None


async def get_fear_greed_index() -> Dict:
    """Get Fear & Greed Index from alternative.me."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.alternative.me/fng/", timeout=10,
                headers=BINANCE_HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()["data"][0]
                return {
                    "value": int(data["value"]),
                    "label": data["value_classification"],
                }
    except Exception:
        pass
    return {"value": 50, "label": "Neutral"}


async def collect_market_data(symbol: str) -> Dict:
    """Collect all market data for a symbol."""
    logger.info(f"📊 Collecting data for {symbol}...")

    # Fetch all data with delays to avoid rate limits
    klines_1d = await get_klines_data(symbol, "1d", 50)
    await asyncio.sleep(0.5)
    klines_4h = await get_klines_data(symbol, "4h", 50)
    await asyncio.sleep(0.5)
    klines_1h = await get_klines_data(symbol, "1h", 100)
    await asyncio.sleep(0.5)
    klines_15m = await get_klines_data(symbol, "15m", 50)
    await asyncio.sleep(0.5)

    ticker = await get_ticker_24h(symbol)
    funding = await get_funding_rate(symbol)
    oi = await get_open_interest(symbol)
    fng = await get_fear_greed_index()

    return {
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_price": ticker.get("price", 0),
        "change_24h_pct": ticker.get("change_pct", 0),
        "volume_24h": ticker.get("volume_24h", 0),
        "high_24h": ticker.get("high_24h", 0),
        "low_24h": ticker.get("low_24h", 0),
        "funding_rate": funding,
        "open_interest": oi,
        "fear_greed": fng,
        "klines": {
            "1d": _summarize_klines(klines_1d, "1D"),
            "4h": _summarize_klines(klines_4h, "4H"),
            "1h": _summarize_klines(klines_1h, "1H"),
            "15m": _summarize_klines(klines_15m, "15M"),
        },
    }


def _summarize_klines(klines: List[Dict], label: str) -> Dict:
    """Summarize klines into key metrics for the prompt."""
    if not klines or len(klines) < 5:
        return {"error": "insufficient data"}

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    volumes = [k["volume"] for k in klines]

    # Simple indicators
    import numpy as np
    closes_arr = np.array(closes)

    # RSI
    deltas = np.diff(closes_arr)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-14:]) if len(gains) >= 14 else np.mean(gains)
    avg_loss = np.mean(losses[-14:]) if len(losses) >= 14 else np.mean(losses)
    rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 50

    # EMAs
    ema20 = float(np.mean(closes_arr[-20:])) if len(closes) >= 20 else float(closes_arr[-1])
    ema50 = float(np.mean(closes_arr[-50:])) if len(closes) >= 50 else float(closes_arr[-1])

    # Recent candles (last 10 as OHLCV)
    recent = klines[-10:]
    recent_summary = [
        f"O:{k['open']:.2f} H:{k['high']:.2f} L:{k['low']:.2f} C:{k['close']:.2f} V:{k['volume']:.0f}"
        for k in recent
    ]

    # Support/Resistance
    support = float(min(lows[-20:])) if len(lows) >= 20 else float(min(lows))
    resistance = float(max(highs[-20:])) if len(highs) >= 20 else float(max(highs))

    # Trend
    if len(closes) >= 20:
        short_ma = np.mean(closes_arr[-10:])
        long_ma = np.mean(closes_arr[-20:])
        trend = "صاعد" if short_ma > long_ma else "هابط" if short_ma < long_ma else "عرضي"
    else:
        trend = "غير محدد"

    # Volume trend
    vol_recent = np.mean(volumes[-5:])
    vol_avg = np.mean(volumes)
    vol_ratio = vol_recent / vol_avg if vol_avg > 0 else 1

    return {
        "timeframe": label,
        "rsi": round(rsi, 1),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "trend": trend,
        "volume_ratio": round(vol_ratio, 2),
        "current_close": round(closes[-1], 2),
        "recent_candles": recent_summary,
    }


# ===== Prompt Builder =====

def build_analysis_prompt(symbol: str, data: Dict) -> str:
    """Build the full Confluence Analysis prompt with real data."""

    klines_section = ""
    for tf, info in data["klines"].items():
        if "error" in info:
            klines_section += f"\n{tf}: بيانات غير كافية"
            continue
        klines_section += f"""
--- {info['timeframe']} ---
الاتجاه: {info['trend']}
RSI(14): {info['rsi']}
EMA20: {info['ema20']} | EMA50: {info['ema50']}
دعم: {info['support']} | مقاومة: {info['resistance']}
نسبة الحجم (حديث/متوسط): {info['volume_ratio']}
آخر 10 شموع:
{chr(10).join(info['recent_candles'])}
"""

    funding_text = f"{data['funding_rate']:.6f}" if data['funding_rate'] is not None else "غير متوفر"
    oi_text = f"{data['open_interest']['oi']:.2f}" if data['open_interest'] else "غير متوفر"
    fng = data['fear_greed']

    prompt = f"""You are an expert financial analyst with 20 years experience.
Analyze {symbol} and provide a high-quality recommendation. Write summary/reasoning in Arabic.

═══════════════════════════════════════
REAL DATA — {symbol}
═══════════════════════════════════════
Price: {data['current_price']}
Change 24h: {data['change_24h_pct']}%
Volume 24h: {data['volume_24h']:,.0f} USDT
High 24h: {data['high_24h']} | Low 24h: {data['low_24h']}
Funding Rate: {funding_text}
Open Interest: {oi_text}
Fear & Greed: {fng['value']} ({fng['label']})

═══════════════════════════════════════
CHART DATA (4 timeframes)
═══════════════════════════════════════
{klines_section}

═══════════════════════════════════════
CONFLUENCE SCORING SYSTEM
═══════════════════════════════════════

Calculate points precisely:

Macro & Sentiment (30 pts):
- Overall trend favorable: +10
- Fear & Greed supports direction: +10  (current: {fng['value']})
- No major negative news: +10

Liquidity (25 pts):
- Price near strong liquidity zone: +10
- Funding Rate neutral or supportive: +8 (current: {funding_text})
- Open Interest growing with movement: +7

Technical (45 pts):
- 3+ timeframes agree: +15
- Order Block أو FVG clear: +12
- Classic indicators confirm: +10
- Clear reliable pattern: +8

Decision:
- <70 = no recommendation
- 70-84 = watch only
- >=85 = recommendation

STRICT RULES:
1. No recommendation if score < 85
2. No recommendation if timeframes conflict
3. Stop loss mandatory
4. R:R لا تقل عن 1:2
5. If uncertain = "no opportunity"

═══════════════════════════════════════
RESPOND WITH JSON ONLY:
═══════════════════════════════════════

{{
  "confluence_score": <0-100>,
  "direction": "<long أو short أو none>",
  "entry_price": "<entry>",
  "tp1": "<target1>",
  "tp2": "<target2>",
  "tp3": "<target3>",
  "stop_loss": "<stop loss>",
  "risk_reward": "<R:R>",
  "timeframe": "<primary timeframe>",
  "duration_minutes": <duration mins>,
  "macro_score": <نقاط الماكرو من 30>,
  "liquidity_score": <نقاط السيولة من 25>,
  "technical_score": <نقاط التحليل الفني من 45>,
  "summary": "<summary IN ARABIC>",
  "key_factors": ["<factor1 IN ARABIC>", "<factor2>"],
  "risks": ["<risk1 IN ARABIC>", "<risk2>"]
}}

If score < 55:
{{
  "confluence_score": <النقاط>,
  "direction": "none",
  "summary": "<reason IN ARABIC>",
  "macro_score": <>,
  "liquidity_score": <>,
  "technical_score": <>
}}
"""
    return prompt


# ===== AI Call Functions =====

async def call_gemini(prompt: str) -> Optional[Dict]:
    """Call Gemini AI via REST API and parse JSON response."""
    if not settings.GEMINI_API_KEY:
        logger.warning("No Gemini API key configured")
        return None

    _track_gemini_call()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GEMINI_API_URL}?key={settings.GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.3,
                        "maxOutputTokens": 1200,
                    },
                },
                timeout=60,
                headers={"Content-Type": "application/json"},
            )

            if resp.status_code == 429:
                logger.warning(f"⚠️🔑 Gemini 429! Quota exhausted! Change API key! Usage today: {_daily_gemini_calls}")
                return None

            if resp.status_code != 200:
                logger.error(f"Gemini API {resp.status_code}: {resp.text[:300]}")
                return None

            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group())

            logger.warning(f"Could not parse Gemini response: {text[:200]}")
            return None

    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return None


async def call_groq(prompt: str) -> Optional[Dict]:
    """Call Groq API (fallback — 14,400 req/day free)."""
    groq_key = getattr(settings, 'GROQ_API_KEY', '')
    if not groq_key:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GROQ_API_URL,
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": "You are a crypto analyst. Reply ONLY with valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1200,
                },
                timeout=30,
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            )
            if resp.status_code == 429:
                logger.warning(f"Groq 429 on primary model, trying gemma2-9b-it...")
                resp = await client.post(
                    GROQ_API_URL,
                    json={
                        "model": "gemma2-9b-it",
                        "messages": [
                            {"role": "system", "content": "You are a crypto analyst. Reply ONLY with valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 1200,
                    },
                    timeout=30,
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                )
            if resp.status_code != 200:
                logger.error(f"Groq API {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group())
            logger.warning(f"Could not parse Groq response: {text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return None


# ===== Main Analysis Function =====

async def analyze_symbol_confluence(symbol: str, base_asset: str) -> Dict:
    """Run full Confluence AI analysis for a symbol."""
    logger.info(f"🧠 Starting Confluence analysis for {symbol}...")

    # Step 1: Collect market data
    data = await collect_market_data(symbol)

    if not data["current_price"]:
        logger.warning(f"No price data for {symbol}, falling back")
        return _fallback_result(symbol)

    # Step 2: Build prompt and call AI
    prompt = build_analysis_prompt(symbol, data)
    # Groq PRIMARY (14,400 req/day, fast)
    groq_key = getattr(settings, "GROQ_API_KEY", "")
    result = None
    if groq_key:
        result = await call_groq(prompt)
        if result:
            logger.info(f"✅ Groq OK for {symbol}")

    # Gemini FALLBACK
    if not result:
        logger.info(f"Groq failed, trying Gemini for {symbol}...")
        result = await call_gemini(prompt)

    if not result:
        logger.error(f"🚨 All AI failed for {symbol}")
        return _gemini_failure_result(symbol, data.get("current_price", 0))

    # Step 3: Parse result — show Gemini's direction as-is
    # The confidence score is informational; filtering happens in signal_generator
    score = result.get("confluence_score", 0)
    direction = result.get("direction", "none")

    if direction == "long":
        decision = "buy"
    elif direction == "short":
        decision = "sell"
    else:
        decision = "no_opportunity"

    # Build analysis result (compatible with existing DB schema)
    analysis_result = {
        "symbol": symbol,
        "decision": decision,
        "confidence_score": min(score, 100),
        "reasoning": _build_reasoning(result, data),
        "is_momentum_real": score >= 70,
        "price_confirmed_news": None,
        "news_source": "AI Confluence",
        "news_title": result.get("summary", ""),
        "news_url": None,
        "technical_indicators": {
            "confluence_score": score,
            "macro_score": result.get("macro_score", 0),
            "liquidity_score": result.get("liquidity_score", 0),
            "technical_score": result.get("technical_score", 0),
            "direction": direction,
            "entry_price": result.get("entry_price"),
            "tp1": result.get("tp1"),
            "tp2": result.get("tp2"),
            "tp3": result.get("tp3"),
            "stop_loss": result.get("stop_loss"),
            "risk_reward": result.get("risk_reward"),
            "timeframe": result.get("timeframe"),
            "duration_minutes": result.get("duration_minutes"),
            "key_factors": result.get("key_factors", []),
            "risks": result.get("risks", []),
            "fear_greed": data["fear_greed"],
            "funding_rate": data["funding_rate"],
            "current_price": data["current_price"],
            "rsi": data["klines"].get("1h", {}).get("rsi"),
            "trend": data["klines"].get("1h", {}).get("trend"),
            "support": data["klines"].get("1h", {}).get("support"),
            "resistance": data["klines"].get("1h", {}).get("resistance"),
            "smc": None,
        },
    }

    logger.info(f"🧠 {symbol}: score={score}, direction={direction}, decision={decision}")
    return analysis_result


def _build_reasoning(result: Dict, data: Dict) -> str:
    """Build human-readable reasoning from Gemini result."""
    lines = []
    score = result.get("confluence_score", 0)
    direction = result.get("direction", "none")

    lines.append(f"📊 نقاط Confluence: {score}/100")
    lines.append(f"🎯 Trend: {'صعود' if direction == 'long' else 'هبوط' if direction == 'short' else 'لا توجد فرصة'}")
    lines.append(f"")
    lines.append(f"الماكرو: {result.get('macro_score', 0)}/30 | السيولة: {result.get('liquidity_score', 0)}/25 | الفني: {result.get('technical_score', 0)}/45")
    lines.append(f"")

    fng = data.get("fear_greed", {})
    lines.append(f"😨 الخوف والطمع: {fng.get('value', '?')} ({fng.get('label', '?')})")

    if data.get("funding_rate") is not None:
        fr = data["funding_rate"]
        lines.append(f"💰 Funding Rate: {fr:.6f} ({'متفائل' if fr > 0 else 'متشائم' if fr < 0 else 'محايد'})")

    summary = result.get("summary", "")
    if summary:
        lines.append(f"")
        lines.append(f"📝 {summary}")

    factors = result.get("key_factors", [])
    if factors:
        lines.append(f"")
        lines.append("✅ العوامل الداعمة:")
        for f in factors:
            lines.append(f"  • {f}")

    risks = result.get("risks", [])
    if risks:
        lines.append(f"")
        lines.append("⚠️ المخاطر:")
        for r in risks:
            lines.append(f"  • {r}")

    if result.get("entry_price"):
        lines.append(f"")
        lines.append(f"🎯 دخول: {result.get('entry_price')} | TP1: {result.get('tp1')} | TP2: {result.get('tp2')} | TP3: {result.get('tp3')}")
        lines.append(f"🛑 وقف: {result.get('stop_loss')} | R:R: {result.get('risk_reward')}")

    return "\n".join(lines)


def _fallback_result(symbol: str) -> Dict:
    """Return a safe 'no opportunity' result when AI fails."""
    return {
        "symbol": symbol,
        "decision": "no_opportunity",
        "confidence_score": 0,
        "reasoning": "⚠️ لم يتمكن المحلل الذكي من التحليل — يرجى المحاولة لاحقاً",
        "is_momentum_real": None,
        "price_confirmed_news": None,
        "news_source": None,
        "news_title": None,
        "news_url": None,
        "technical_indicators": {},
    }


def _gemini_failure_result(symbol: str, current_price: float = 0) -> Dict:
    """Return a clear failure result when all AI providers are down — NO fallback to classic."""
    return {
        "symbol": symbol,
        "decision": "no_opportunity",
        "confidence_score": 0,
        "reasoning": f"🚨 تعطّل الذكاء الاصطناعي\n⚠️🔑 بدّل مفتاح Gemini! استخدام اليوم: {_daily_gemini_calls} طلب\n🔧 https://aistudio.google.com/apikey",
        "is_momentum_real": None,
        "price_confirmed_news": None,
        "news_source": "AI (FAILED)",
        "news_title": "🚨 AI متعطل",
        "news_url": None,
        "technical_indicators": {
            "current_price": current_price,
            "ai_status": "failed",
        },
    }
