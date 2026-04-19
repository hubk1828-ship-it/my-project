"""
Confluence Analyzer — AI-Powered Analysis Engine
Uses Google Gemini AI with real Binance data for 6-layer analysis.
Fallback to classic analyzer if Gemini fails.
"""

import json
import re
import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timezone

import httpx
import google.generativeai as genai

from app.core.config import get_settings
from app.services.binance_client import (
    _request_with_retry, BINANCE_HEADERS, _price_cache, get_prices_batch
)

settings = get_settings()
logger = logging.getLogger("confluence")

# Configure Gemini
if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)


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

    prompt = f"""أنت محلل مالي واقتصادي وخبير في التحليل الفني بخبرة 20 عاماً.
مهمتك تحليل {symbol} وإعطاء توصية عالية الجودة فقط.

═══════════════════════════════════════
البيانات الحقيقية — {symbol}
═══════════════════════════════════════
السعر الحالي: {data['current_price']}
التغير 24h: {data['change_24h_pct']}%
حجم التداول 24h: {data['volume_24h']:,.0f} USDT
أعلى 24h: {data['high_24h']} | أدنى 24h: {data['low_24h']}
Funding Rate: {funding_text}
Open Interest: {oi_text}
مؤشر الخوف والطمع: {fng['value']} ({fng['label']})

═══════════════════════════════════════
بيانات الشارت (4 فريمات)
═══════════════════════════════════════
{klines_section}

═══════════════════════════════════════
المطلوب — نظام Confluence Scoring
═══════════════════════════════════════

حلل البيانات أعلاه واحسب النقاط بدقة:

الماكرو والمعنويات (30 نقطة):
- الاتجاه الكلي مواتٍ: +10
- Fear & Greed يدعم الاتجاه: +10  (الحالي: {fng['value']})
- لا أخبار سلبية كبرى: +10

السيولة (25 نقطة):
- السعر قرب منطقة سيولة قوية: +10
- Funding Rate محايد أو يدعم: +8 (الحالي: {funding_text})
- Open Interest يتزايد مع الحركة: +7

التحليل الفني (45 نقطة):
- اتفاق 3+ فريمات على نفس الاتجاه: +15
- Order Block أو FVG واضح: +12
- مؤشرات كلاسيكية تؤكد: +10
- نمط واضح وموثوق: +8

القرار:
- أقل من 70 → لا توصية
- 70-84 → مراقبة فقط
- 85-100 → توصية

القواعد الصارمة:
1. لا توصية إذا النقاط أقل من 85
2. لا توصية إذا الفريمات متعارضة
3. وقف الخسارة إلزامي
4. نسبة R:R لا تقل عن 1:2
5. إذا شككت، قل "لا توجد فرصة"

═══════════════════════════════════════
أجب بـ JSON فقط (بدون أي نص آخر):
═══════════════════════════════════════

{{
  "confluence_score": <رقم من 0-100>,
  "direction": "<long أو short أو none>",
  "entry_price": "<سعر الدخول>",
  "tp1": "<هدف 1>",
  "tp2": "<هدف 2>",
  "tp3": "<هدف 3>",
  "stop_loss": "<وقف الخسارة>",
  "risk_reward": "<نسبة R:R>",
  "timeframe": "<الفريم الأساسي>",
  "duration_minutes": <مدة الصفقة بالدقائق>,
  "macro_score": <نقاط الماكرو من 30>,
  "liquidity_score": <نقاط السيولة من 25>,
  "technical_score": <نقاط التحليل الفني من 45>,
  "summary": "<ملخص التحليل بالعربي>",
  "key_factors": ["<عامل 1>", "<عامل 2>"],
  "risks": ["<خطر 1>", "<خطر 2>"]
}}

إذا النقاط أقل من 85، أرجع:
{{
  "confluence_score": <النقاط>,
  "direction": "none",
  "summary": "<سبب عدم التوصية بالعربي>",
  "macro_score": <>,
  "liquidity_score": <>,
  "technical_score": <>
}}
"""
    return prompt


# ===== Gemini AI Call =====

async def call_gemini(prompt: str) -> Optional[Dict]:
    """Call Gemini AI and parse JSON response."""
    if not settings.GEMINI_API_KEY:
        logger.warning("No Gemini API key configured")
        return None

    try:
        model = genai.GenerativeModel("gemini-2.0-flash-lite")
        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=2000,
            ),
        )

        text = response.text.strip()

        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json.loads(json_match.group())

        logger.warning(f"Could not parse Gemini response: {text[:200]}")
        return None

    except Exception as e:
        logger.error(f"Gemini API error: {e}")
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

    # Step 2: Build prompt and call Gemini (with rate limit pause)
    await asyncio.sleep(5)  # Respect Gemini rate limits
    prompt = build_analysis_prompt(symbol, data)
    result = await call_gemini(prompt)

    if not result:
        logger.warning(f"Gemini failed for {symbol}, falling back")
        return _fallback_result(symbol)

    # Step 3: Parse result
    score = result.get("confluence_score", 0)
    direction = result.get("direction", "none")

    if direction == "none" or score < 85:
        decision = "no_opportunity"
    elif direction == "long":
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
        "news_source": "Gemini AI Confluence",
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
    lines.append(f"🎯 الاتجاه: {'صعود' if direction == 'long' else 'هبوط' if direction == 'short' else 'لا توجد فرصة'}")
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
