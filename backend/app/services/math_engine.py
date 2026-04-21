"""
Math Engine — Correct mathematical indicators for trading.
Replaces all broken SMA-as-EMA calculations with proper algorithms.
"""
import numpy as np
from typing import Dict, List, Optional, Tuple


# ===== Core EMA (Exponential Moving Average) =====

def ema(data: List[float], period: int) -> np.ndarray:
    """True EMA: α = 2/(N+1), EMA_t = α × C + (1-α) × EMA_{t-1}"""
    arr = np.array(data, dtype=float)
    if len(arr) < period:
        return arr
    alpha = 2.0 / (period + 1)
    result = np.zeros_like(arr)
    result[0] = arr[0]
    for i in range(1, len(arr)):
        result[i] = alpha * arr[i] + (1 - alpha) * result[i - 1]
    return result


def sma(data: List[float], period: int) -> np.ndarray:
    """Simple Moving Average."""
    arr = np.array(data, dtype=float)
    if len(arr) < period:
        return arr
    result = np.full_like(arr, np.nan)
    for i in range(period - 1, len(arr)):
        result[i] = np.mean(arr[i - period + 1: i + 1])
    return result


# ===== RSI (Wilder's Smoothed) =====

def rsi_wilder(closes: List[float], period: int = 14) -> float:
    """
    Correct RSI using Wilder's Smoothing:
    avg_gain = (prev_avg_gain × 13 + current_gain) / 14
    """
    arr = np.array(closes, dtype=float)
    if len(arr) < period + 1:
        return 50.0

    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # First average: simple mean of first N periods
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    # Wilder's smoothing for remaining
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


# ===== ATR (Average True Range) =====

def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    """
    ATR = Wilder's EMA of True Range.
    TR = max(H-L, |H-C_prev|, |L-C_prev|)
    """
    h = np.array(highs, dtype=float)
    l = np.array(lows, dtype=float)
    c = np.array(closes, dtype=float)

    if len(c) < period + 1:
        return float(np.mean(h - l)) if len(h) > 0 else 0.0

    tr = np.zeros(len(c))
    tr[0] = h[0] - l[0]
    for i in range(1, len(c)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))

    # Wilder's smoothing
    atr_val = np.mean(tr[:period])
    for i in range(period, len(tr)):
        atr_val = (atr_val * (period - 1) + tr[i]) / period

    return round(atr_val, 6)


def atr_series(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> np.ndarray:
    """Full ATR series for Keltner/position sizing."""
    h = np.array(highs, dtype=float)
    l = np.array(lows, dtype=float)
    c = np.array(closes, dtype=float)

    tr = np.zeros(len(c))
    tr[0] = h[0] - l[0]
    for i in range(1, len(c)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))

    result = np.zeros_like(tr)
    result[period - 1] = np.mean(tr[:period])
    for i in range(period, len(tr)):
        result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    return result


# ===== MACD =====

def macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
    """MACD = EMA(12) - EMA(26), Signal = EMA(9) of MACD."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line.tolist(), signal)
    histogram = macd_line - signal_line

    return {
        "macd": round(float(macd_line[-1]), 6),
        "signal": round(float(signal_line[-1]), 6),
        "histogram": round(float(histogram[-1]), 6),
        "histogram_prev": round(float(histogram[-2]), 6) if len(histogram) > 1 else 0,
        "bullish_cross": float(histogram[-1]) > 0 and float(histogram[-2]) <= 0 if len(histogram) > 1 else False,
        "bearish_cross": float(histogram[-1]) < 0 and float(histogram[-2]) >= 0 if len(histogram) > 1 else False,
    }


# ===== Bollinger Bands =====

def bollinger_bands(closes: List[float], period: int = 20, std_dev: float = 2.0) -> Dict:
    """Bollinger Bands: Middle=SMA(20), Upper/Lower=±2σ."""
    arr = np.array(closes, dtype=float)
    if len(arr) < period:
        mid = float(arr[-1])
        return {"upper": mid, "middle": mid, "lower": mid, "pct_b": 0.5, "bandwidth": 0}

    middle = float(np.mean(arr[-period:]))
    std = float(np.std(arr[-period:], ddof=1))
    upper = middle + std_dev * std
    lower = middle - std_dev * std

    price = float(arr[-1])
    pct_b = (price - lower) / (upper - lower) if upper != lower else 0.5
    bandwidth = (upper - lower) / middle if middle > 0 else 0

    return {
        "upper": round(upper, 6),
        "middle": round(middle, 6),
        "lower": round(lower, 6),
        "pct_b": round(pct_b, 4),
        "bandwidth": round(bandwidth, 6),
    }


# ===== Fibonacci Retracement & Extension =====

PHI = 1.6180339887  # Golden Ratio

FIBO_RETRACEMENT = [0.236, 0.382, 0.500, 0.618, 0.786]
FIBO_EXTENSION = [1.0, 1.272, PHI, 2.0, 2.618]


def fibonacci_levels(swing_high: float, swing_low: float) -> Dict:
    """
    Fibonacci retracement + extension levels.
    Uses Golden Ratio φ = 1.618.
    """
    diff = swing_high - swing_low
    if diff <= 0:
        return {"retracement": {}, "extension": {}, "direction": "none"}

    retracement = {}
    for level in FIBO_RETRACEMENT:
        retracement[level] = round(swing_high - diff * level, 6)

    extension = {}
    for level in FIBO_EXTENSION:
        extension[level] = round(swing_low + diff * level, 6)  # bullish extension
        extension[-level] = round(swing_high - diff * level, 6)  # bearish extension

    return {"retracement": retracement, "extension": extension}


def find_swing_points(highs: List[float], lows: List[float], lookback: int = 20) -> Tuple[float, float]:
    """Find swing high/low from recent data."""
    h = np.array(highs[-lookback * 3:], dtype=float) if len(highs) > lookback else np.array(highs, dtype=float)
    l = np.array(lows[-lookback * 3:], dtype=float) if len(lows) > lookback else np.array(lows, dtype=float)

    swing_high = float(np.max(h))
    swing_low = float(np.min(l))
    return swing_high, swing_low


# ===== VWAP =====

def vwap(highs: List[float], lows: List[float], closes: List[float], volumes: List[float]) -> float:
    """VWAP = Σ(Typical_Price × Volume) / Σ(Volume)."""
    h = np.array(highs, dtype=float)
    l = np.array(lows, dtype=float)
    c = np.array(closes, dtype=float)
    v = np.array(volumes, dtype=float)

    typical = (h + l + c) / 3.0
    total_vol = np.sum(v)
    if total_vol == 0:
        return float(c[-1])
    return round(float(np.sum(typical * v) / total_vol), 6)


# ===== Stochastic RSI =====

def stochastic_rsi(closes: List[float], rsi_period: int = 14, stoch_period: int = 14, k_smooth: int = 3) -> Dict:
    """Stochastic RSI: %K = (RSI - min(RSI)) / (max(RSI) - min(RSI))."""
    arr = np.array(closes, dtype=float)
    if len(arr) < rsi_period + stoch_period:
        return {"k": 50.0, "d": 50.0}

    # Compute RSI series
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    rsi_values = []
    avg_g = np.mean(gains[:rsi_period])
    avg_l = np.mean(losses[:rsi_period])
    for i in range(rsi_period, len(gains)):
        avg_g = (avg_g * (rsi_period - 1) + gains[i]) / rsi_period
        avg_l = (avg_l * (rsi_period - 1) + losses[i]) / rsi_period
        rs = avg_g / avg_l if avg_l > 0 else 100
        rsi_values.append(100.0 - (100.0 / (1.0 + rs)))

    if len(rsi_values) < stoch_period:
        return {"k": 50.0, "d": 50.0}

    rsi_arr = np.array(rsi_values)
    k_values = []
    for i in range(stoch_period - 1, len(rsi_arr)):
        window = rsi_arr[i - stoch_period + 1: i + 1]
        rsi_min = np.min(window)
        rsi_max = np.max(window)
        k = ((rsi_arr[i] - rsi_min) / (rsi_max - rsi_min) * 100) if rsi_max != rsi_min else 50
        k_values.append(k)

    if len(k_values) < k_smooth:
        return {"k": round(k_values[-1], 2) if k_values else 50.0, "d": 50.0}

    k_val = float(np.mean(k_values[-k_smooth:]))
    d_val = float(np.mean(k_values[-k_smooth * 2:])) if len(k_values) >= k_smooth * 2 else k_val

    return {"k": round(k_val, 2), "d": round(d_val, 2)}


# ===== Support & Resistance (Volume-weighted pivots) =====

def compute_support_resistance(highs: List[float], lows: List[float], closes: List[float],
                                volumes: List[float], lookback: int = 50) -> Dict:
    """Volume-weighted pivot-based support and resistance."""
    h = np.array(highs[-lookback:], dtype=float)
    l = np.array(lows[-lookback:], dtype=float)
    c = np.array(closes[-lookback:], dtype=float)
    v = np.array(volumes[-lookback:], dtype=float)

    # Find local minima/maxima with volume weighting
    supports = []
    resistances = []

    for i in range(2, len(c) - 2):
        # Local minimum
        if l[i] <= l[i - 1] and l[i] <= l[i - 2] and l[i] <= l[i + 1] and l[i] <= l[i + 2]:
            supports.append((float(l[i]), float(v[i])))
        # Local maximum
        if h[i] >= h[i - 1] and h[i] >= h[i - 2] and h[i] >= h[i + 1] and h[i] >= h[i + 2]:
            resistances.append((float(h[i]), float(v[i])))

    # Weight by volume and take top 3
    supports.sort(key=lambda x: x[1], reverse=True)
    resistances.sort(key=lambda x: x[1], reverse=True)

    sup = supports[0][0] if supports else float(np.min(l))
    res = resistances[0][0] if resistances else float(np.max(h))

    return {
        "support": round(sup, 6),
        "resistance": round(res, 6),
        "support_levels": [round(s[0], 6) for s in supports[:3]],
        "resistance_levels": [round(r[0], 6) for r in resistances[:3]],
    }


# ===== Trend Detection =====

def detect_trend(closes: List[float]) -> Dict:
    """Multi-EMA trend detection."""
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50)

    e9 = float(ema9[-1])
    e21 = float(ema21[-1])
    e50 = float(ema50[-1]) if len(closes) >= 50 else e21

    if e9 > e21 > e50:
        trend = "strong_bullish"
        strength = 2
    elif e9 > e21:
        trend = "bullish"
        strength = 1
    elif e9 < e21 < e50:
        trend = "strong_bearish"
        strength = -2
    elif e9 < e21:
        trend = "bearish"
        strength = -1
    else:
        trend = "sideways"
        strength = 0

    return {"trend": trend, "strength": strength, "ema9": round(e9, 6), "ema21": round(e21, 6), "ema50": round(e50, 6)}


# ===== Master Function =====

def compute_all_indicators(closes: List[float], highs: List[float], lows: List[float],
                           volumes: List[float]) -> Dict:
    """Compute ALL indicators from raw OHLCV data — single call."""
    if not closes or len(closes) < 5:
        return {"error": "insufficient data"}

    price = closes[-1]

    # Core indicators
    rsi_val = rsi_wilder(closes)
    atr_val = atr(highs, lows, closes)
    macd_data = macd(closes)
    bb = bollinger_bands(closes)
    stoch = stochastic_rsi(closes)
    trend = detect_trend(closes)
    sr = compute_support_resistance(highs, lows, closes, volumes)
    vwap_val = vwap(highs, lows, closes, volumes)

    # Fibonacci
    swing_high, swing_low = find_swing_points(highs, lows)
    fib = fibonacci_levels(swing_high, swing_low)

    # EMA values
    ema9 = trend["ema9"]
    ema21 = trend["ema21"]
    ema50 = trend["ema50"]
    ema_arr_20 = ema(closes, 20)
    ema20 = float(ema_arr_20[-1])

    # Volume analysis
    vol_arr = np.array(volumes, dtype=float)
    vol_recent = float(np.mean(vol_arr[-5:])) if len(vol_arr) >= 5 else float(vol_arr[-1])
    vol_avg = float(np.mean(vol_arr)) if len(vol_arr) > 0 else 1
    volume_ratio = round(vol_recent / vol_avg, 2) if vol_avg > 0 else 1.0

    return {
        "price": price,
        "rsi": rsi_val,
        "atr": atr_val,
        "atr_pct": round(atr_val / price * 100, 4) if price > 0 else 0,
        "macd": macd_data["macd"],
        "macd_signal": macd_data["signal"],
        "macd_histogram": macd_data["histogram"],
        "macd_histogram_prev": macd_data["histogram_prev"],
        "macd_bullish_cross": macd_data["bullish_cross"],
        "macd_bearish_cross": macd_data["bearish_cross"],
        "bb_upper": bb["upper"],
        "bb_middle": bb["middle"],
        "bb_lower": bb["lower"],
        "bb_pct_b": bb["pct_b"],
        "bb_bandwidth": bb["bandwidth"],
        "stoch_k": stoch["k"],
        "stoch_d": stoch["d"],
        "ema9": ema9,
        "ema20": ema20,
        "ema21": ema21,
        "ema50": ema50,
        "trend": trend["trend"],
        "trend_strength": trend["strength"],
        "support": sr["support"],
        "resistance": sr["resistance"],
        "support_levels": sr["support_levels"],
        "resistance_levels": sr["resistance_levels"],
        "vwap": vwap_val,
        "volume_ratio": volume_ratio,
        "swing_high": swing_high,
        "swing_low": swing_low,
        "fib_retracement": fib["retracement"],
        "fib_extension": fib["extension"],
    }


# ===== Mathematical Confluence Score =====

def compute_confluence_score(indicators: Dict, direction: str = "auto") -> Dict:
    """
    Compute confluence score MATHEMATICALLY — no AI guessing.
    Returns score 0-100 with breakdown.
    """
    price = indicators.get("price", 0)
    if price <= 0:
        return {"score": 0, "direction": "none", "breakdown": {}}

    long_score = 0
    short_score = 0
    breakdown_long = {}
    breakdown_short = {}

    rsi = indicators.get("rsi", 50)
    # RSI — weight 15
    if rsi < 30:
        long_score += 15
        breakdown_long["rsi"] = f"RSI={rsi} (oversold ✓)"
    elif rsi < 40:
        long_score += 8
        breakdown_long["rsi"] = f"RSI={rsi} (approaching oversold)"
    if rsi > 70:
        short_score += 15
        breakdown_short["rsi"] = f"RSI={rsi} (overbought ✓)"
    elif rsi > 60:
        short_score += 8
        breakdown_short["rsi"] = f"RSI={rsi} (approaching overbought)"

    # EMA Alignment — weight 15
    ts = indicators.get("trend_strength", 0)
    if ts >= 2:
        long_score += 15
        breakdown_long["ema"] = "EMA9>EMA21>EMA50 (strong bullish ✓)"
    elif ts == 1:
        long_score += 8
        breakdown_long["ema"] = "EMA9>EMA21 (bullish)"
    if ts <= -2:
        short_score += 15
        breakdown_short["ema"] = "EMA9<EMA21<EMA50 (strong bearish ✓)"
    elif ts == -1:
        short_score += 8
        breakdown_short["ema"] = "EMA9<EMA21 (bearish)"

    # MACD — weight 12
    if indicators.get("macd_bullish_cross"):
        long_score += 12
        breakdown_long["macd"] = "MACD bullish cross ✓"
    elif indicators.get("macd_histogram", 0) > 0:
        long_score += 6
        breakdown_long["macd"] = "MACD histogram positive"
    if indicators.get("macd_bearish_cross"):
        short_score += 12
        breakdown_short["macd"] = "MACD bearish cross ✓"
    elif indicators.get("macd_histogram", 0) < 0:
        short_score += 6
        breakdown_short["macd"] = "MACD histogram negative"

    # Bollinger — weight 15
    pct_b = indicators.get("bb_pct_b", 0.5)
    if pct_b < 0.05:
        long_score += 15
        breakdown_long["bb"] = f"%B={pct_b:.3f} (at lower band ✓)"
    elif pct_b < 0.2:
        long_score += 8
        breakdown_long["bb"] = f"%B={pct_b:.3f} (near lower band)"
    if pct_b > 0.95:
        short_score += 15
        breakdown_short["bb"] = f"%B={pct_b:.3f} (at upper band ✓)"
    elif pct_b > 0.8:
        short_score += 8
        breakdown_short["bb"] = f"%B={pct_b:.3f} (near upper band)"

    # Fibonacci proximity — weight 13
    fib_ret = indicators.get("fib_retracement", {})
    for level in [0.382, 0.5, 0.618]:
        fib_price = fib_ret.get(level, 0)
        if fib_price > 0 and abs(price - fib_price) / price < 0.005:
            long_score += 13
            breakdown_long["fib"] = f"Price at Fib {level} ({fib_price:.2f}) ✓"
            short_score += 13
            breakdown_short["fib"] = f"Price at Fib {level} ({fib_price:.2f}) ✓"
            break

    # Volume — weight 10
    vr = indicators.get("volume_ratio", 1)
    if vr > 1.5:
        long_score += 10
        short_score += 10
        breakdown_long["volume"] = f"Vol ratio={vr}× (confirmed ✓)"
        breakdown_short["volume"] = f"Vol ratio={vr}× (confirmed ✓)"
    elif vr > 1.2:
        long_score += 5
        short_score += 5

    # VWAP — weight 10
    vwap_val = indicators.get("vwap", price)
    if price > vwap_val:
        long_score += 10
        breakdown_long["vwap"] = f"Above VWAP ({vwap_val:.2f}) ✓"
    else:
        short_score += 10
        breakdown_short["vwap"] = f"Below VWAP ({vwap_val:.2f}) ✓"

    # Stochastic RSI — weight 10
    stoch_k = indicators.get("stoch_k", 50)
    if stoch_k < 20:
        long_score += 10
        breakdown_long["stoch"] = f"StochRSI K={stoch_k} (oversold ✓)"
    if stoch_k > 80:
        short_score += 10
        breakdown_short["stoch"] = f"StochRSI K={stoch_k} (overbought ✓)"

    # Determine direction
    if direction == "auto":
        if long_score >= short_score and long_score >= 55:
            direction = "long"
        elif short_score > long_score and short_score >= 55:
            direction = "short"
        else:
            direction = "none"

    score = long_score if direction == "long" else short_score if direction == "short" else max(long_score, short_score)
    breakdown = breakdown_long if direction == "long" else breakdown_short if direction == "short" else {}

    return {
        "score": min(score, 100),
        "direction": direction,
        "long_score": long_score,
        "short_score": short_score,
        "breakdown": breakdown,
    }
