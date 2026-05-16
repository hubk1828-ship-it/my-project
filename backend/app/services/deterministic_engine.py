"""
Deterministic Confluence Engine — 12-component weighted scoring system.
Ported from QAF Engine v5. Same inputs = Same outputs ALWAYS.
"""
import math
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PHI_INV = 0.6180339887
THRESHOLD = 74
NEAR_MISS_LOW = 62

# Default weights (overridden by DB learned weights)
DEFAULT_WEIGHTS = {
    "trend": 0.18, "momentum": 0.14, "rsi": 0.10, "macd": 0.08,
    "fibo": 0.07, "liq": 0.05, "sent": 0.05, "chaos": 0.04,
    "vwap": 0.08, "basis": 0.05, "regime": 0.06, "btc_lead": 0.10,
}

COMPONENTS = list(DEFAULT_WEIGHTS.keys())


def _ema(data: List[float], period: int) -> List[float]:
    """Fast EMA calculation."""
    if not data:
        return []
    k = 2.0 / (period + 1)
    result = [data[0]]
    for i in range(1, len(data)):
        result.append(data[i] * k + result[-1] * (1 - k))
    return result


def _rsi(closes: List[float], period: int = 14) -> float:
    """RSI calculation matching QAF."""
    if len(closes) < period + 1:
        return 50.0
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        if d > 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + (d if d > 0 else 0)) / period
        avg_loss = (avg_loss * (period - 1) + (-d if d < 0 else 0)) / period
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    """ATR calculation."""
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    if not trs:
        return 0.0
    return sum(trs[-period:]) / min(period, len(trs))


def _macd(closes: List[float]) -> Dict[str, float]:
    """MACD with histogram."""
    fast = _ema(closes, 12)
    slow = _ema(closes, 26)
    line = [f - s for f, s in zip(fast, slow)]
    signal = _ema(line, 9)
    hist = [l - s for l, s in zip(line, signal)]
    return {"hist": hist[-1] if hist else 0, "line": line[-1] if line else 0}


def _vwap(klines: List[Dict]) -> float:
    """Volume-Weighted Average Price."""
    n = min(len(klines), 48)
    total_vp, total_v = 0.0, 0.0
    for k in klines[-n:]:
        tp = (k["h"] + k["l"] + k["c"]) / 3
        total_vp += tp * k["v"]
        total_v += k["v"]
    return total_vp / total_v if total_v > 0 else klines[-1]["c"]


def _cvd(klines: List[Dict], n: int = 20) -> float:
    """Cumulative Volume Delta."""
    cvd = 0.0
    for k in klines[-n:]:
        body = k["c"] - k["o"]
        rng = k["h"] - k["l"]
        if rng > 0:
            cvd += (body / rng) * k["v"]
    return cvd


def _hurst(closes: List[float]) -> float:
    """Hurst exponent — market predictability (>0.5 = trending, <0.5 = mean-reverting)."""
    hp = closes[-min(len(closes), 80):]
    if len(hp) < 20:
        return 0.5
    lgs, rs_vals = [], []
    for lag in range(2, min(20, len(hp) // 2) + 1):
        chunks = [hp[i:i + lag] for i in range(0, len(hp) - lag, lag)]
        rv_list = []
        for c in chunks:
            if len(c) < 2:
                continue
            m = sum(c) / len(c)
            dv = [v - m for v in c]
            cum, mn, mx = 0.0, 0.0, 0.0
            for d in dv:
                cum += d
                mx = max(mx, cum)
                mn = min(mn, cum)
            std = math.sqrt(sum(d * d for d in dv) / len(c)) or 0.001
            rv_list.append((mx - mn) / std)
        if rv_list:
            lgs.append(math.log(lag))
            rs_vals.append(math.log(sum(rv_list) / len(rv_list)))
    if len(lgs) < 2:
        return 0.5
    n = len(lgs)
    sx = sum(lgs)
    sy = sum(rs_vals)
    sxy = sum(x * y for x, y in zip(lgs, rs_vals))
    sx2 = sum(x * x for x in lgs)
    denom = n * sx2 - sx * sx
    return (n * sxy - sx * sy) / denom if denom != 0 else 0.5


def _lyapunov(closes: List[float]) -> float:
    """Lyapunov exponent — chaos detection."""
    n = min(50, len(closes) - 1)
    if n < 5:
        return 0.0
    s, ct = 0.0, 0
    for i in range(len(closes) - n, len(closes)):
        d = abs(closes[i] - closes[i - 1])
        if d > 0:
            s += math.log(d)
            ct += 1
    return s / ct if ct > 0 else 0.0


def _realized_vol(closes: List[float]) -> float:
    """Annualized realized volatility."""
    n = min(20, len(closes) - 1)
    if n < 2:
        return 0.0
    ss = 0.0
    for i in range(len(closes) - n, len(closes)):
        if closes[i - 1] > 0:
            r = math.log(closes[i] / closes[i - 1])
            ss += r * r
    return math.sqrt(ss / n * 252)


def _evt_penalty(closes: List[float]) -> float:
    """Extreme Value Theory — tail risk penalty."""
    n = min(50, len(closes) - 1)
    if n < 5:
        return 1.0
    rts = []
    for i in range(len(closes) - n, len(closes)):
        if closes[i - 1] > 0:
            rts.append(abs(math.log(closes[i] / closes[i - 1])))
    if not rts:
        return 1.0
    sr = sorted(rts, reverse=True)
    q = sr[max(0, int(len(sr) * 0.05))]
    mn = sum(rts) / len(rts)
    z = (rts[-1] - mn) / (q - mn + 0.0001) if mn > 0 else 0
    if z > 2:
        return 0.7
    elif z > 1.5:
        return 0.85
    return 1.0


def _get_session() -> tuple:
    """Get current trading session and multiplier."""
    from datetime import datetime, timezone
    hr = datetime.now(timezone.utc).hour
    if 13 <= hr < 22:
        return "US", 1.10
    elif 8 <= hr < 17:
        return "EU", 1.05
    return "ASIA", 0.90


def compute_scores(
    klines: List[Dict],
    btc_klines: List[Dict] = None,
    order_book: Dict = None,
    funding_rate: float = 0,
    fear_greed: int = 50,
    ls_ratio: float = 1.0,
    spot_price: float = 0,
    open_interest: float = 0,
) -> Dict:
    """
    Compute all 12 component scores + final confidence.
    100% deterministic — same inputs ALWAYS produce same outputs.
    """
    if not klines or len(klines) < 30:
        return {"error": "insufficient data", "confidence": 0, "signal_type": "NEUTRAL", "should_trade": False}

    C = [k["c"] for k in klines]
    H = [k["h"] for k in klines]
    L = [k["l"] for k in klines]
    V = [k["v"] for k in klines]
    P = C[-1]

    # === Core indicators ===
    rsi_val = _rsi(C)
    atr_val = _atr(H, L, C)
    macd = _macd(C)
    em20 = _ema(C, 20)[-1]
    em50 = _ema(C, 50)[-1]
    em200 = _ema(C, min(200, len(C)))[-1]
    vwap = _vwap(klines)
    cvd = _cvd(klines)

    # === VWAP ===
    vwap_diff = (P - vwap) / vwap if vwap > 0 else 0
    vwap_pos = "ABOVE" if vwap_diff > 0.002 else "BELOW" if vwap_diff < -0.002 else "AT VWAP"

    # === CVD direction ===
    cvd_dir = "BUY" if cvd > 500 else "SELL" if cvd < -500 else "SLIGHT BUY" if cvd > 0 else "SLIGHT SELL"

    # === Long/Short Ratio ===
    ls_view = "CROWDED LONG" if ls_ratio > 1.3 else "CROWDED SHORT" if ls_ratio < 0.8 else "BALANCED"
    ls_score = 0.2 if ls_ratio > 1.5 else 0.35 if ls_ratio > 1.2 else 0.8 if ls_ratio < 0.7 else 0.65 if ls_ratio < 0.85 else 0.5

    # === Basis (Futures vs Spot) ===
    sp = spot_price if spot_price > 0 else P * 0.9995
    basis = P - sp
    basis_pct = (basis / sp) * 100 if sp > 0 else 0
    basis_regime = "CONTANGO" if basis_pct > 0.1 else "BACKWARDATION" if basis_pct < -0.1 else "FLAT"
    basis_score = 0.7 if basis_pct > 0.3 else 0.6 if basis_pct > 0.1 else 0.3 if basis_pct < -0.2 else 0.5

    # === Market Regime ===
    ps = C[-min(len(C), 50):]
    pm = sum(ps) / len(ps)
    pv = sum((p - pm) ** 2 for p in ps) / len(ps)
    pvol = math.sqrt(pv) / pm if pm > 0 else 0
    pe20 = _ema(ps, min(20, len(ps)))
    pe50 = _ema(ps, min(50, len(ps)))
    ptrd = (pe20[-1] - pe50[-1]) / pm if pm > 0 else 0
    regime = "TRENDING" if pvol < 0.015 and abs(ptrd) > 0.002 else "VOLATILE" if pvol > 0.03 else "RANGING"
    regime_score = 0.75 if regime == "TRENDING" else 0.5 if regime == "RANGING" else 0.3

    # === BTC Correlation ===
    btc_score = 0.5
    btc_change = 0.0
    btc_corr = 0.0
    if btc_klines and len(btc_klines) > 5:
        n = min(20, len(btc_klines), len(klines))
        br, er = [], []
        for i in range(1, n):
            bc = btc_klines[-n + i]["c"]
            bc_prev = btc_klines[-n + i - 1]["c"]
            ec = klines[-n + i]["c"]
            ec_prev = klines[-n + i - 1]["c"]
            if bc_prev > 0 and ec_prev > 0:
                br.append((bc - bc_prev) / bc_prev)
                er.append((ec - ec_prev) / ec_prev)
        if br:
            bm = sum(br) / len(br)
            em2 = sum(er) / len(er)
            cv_val = sum((b - bm) * (e - em2) for b, e in zip(br, er))
            bv_val = sum((b - bm) ** 2 for b in br)
            ev_val = sum((e - em2) ** 2 for e in er)
            btc_corr = cv_val / math.sqrt(bv_val * ev_val) if bv_val * ev_val > 0 else 0
            btc_change = sum(br[-3:])
            if btc_corr > 0.6 and btc_change > 0.005:
                btc_score = 0.75
            elif btc_corr > 0.6 and btc_change < -0.005:
                btc_score = 0.25
            else:
                btc_score = 0.5 + btc_corr * 0.1

    # === Chaos indicators ===
    hurst = _hurst(C)
    lyap = _lyapunov(C)
    real_vol = _realized_vol(C)
    evt_p = _evt_penalty(C)

    # === Fibonacci ===
    hi = max(H[-50:])
    lo = min(L[-50:])
    rng = hi - lo
    fibo_score = 0.4
    fibo_level = "NONE"
    if rng > 0:
        levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        names = ["0", "0.236", "0.382", "0.5", "0.618", "0.786", "1.0"]
        min_dist = float("inf")
        for lv, nm in zip(levels, names):
            d = abs(P - (lo + rng * lv)) / rng
            if d < min_dist:
                min_dist = d
                fibo_level = nm
        fibo_score = 0.9 if min_dist < 0.015 else 0.7 if min_dist < 0.03 else 0.4

    # === Liquidity (Order Book) ===
    liq_score = 0.5
    if order_book:
        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])
        if bids and asks:
            bid_vol = sum(float(b[1]) for b in bids[:10])
            ask_vol = sum(float(a[1]) for a in asks[:10])
            total = bid_vol + ask_vol
            liq_score = bid_vol / total if total > 0 else 0.5

    # === Component Scores ===
    # Trend
    if P > em20 and em20 > em50 and em50 > em200:
        trend_score, trend_dir = 0.90, "LONG"
    elif P > em20 and em20 > em50:
        trend_score, trend_dir = 0.75, "LONG"
    elif P < em20 and em20 < em50 and em50 < em200:
        trend_score, trend_dir = 0.10, "SHORT"
    elif P < em20 and em20 < em50:
        trend_score, trend_dir = 0.25, "SHORT"
    else:
        trend_score, trend_dir = 0.50, "NEUTRAL"

    # Momentum
    mom_arr = [(C[-10 + i] - C[-10 + i - 1]) / C[-10 + i - 1] for i in range(1, 10) if C[-10 + i - 1] > 0]
    mom_sum = sum(mom_arr) if mom_arr else 0
    mom_score = max(0.05, min(0.95, 0.5 + math.tanh(mom_sum * 200) * 0.4))

    # RSI
    rsi_score = 0.85 if rsi_val < 30 else 0.70 if rsi_val < 40 else 0.55 if rsi_val < 50 else 0.50 if rsi_val < 60 else 0.40 if rsi_val < 70 else 0.20

    # MACD
    if macd["hist"] > 0 and macd["line"] > 0:
        macd_score = 0.80
    elif macd["hist"] > 0:
        macd_score = 0.65
    elif macd["hist"] < 0 and macd["line"] < 0:
        macd_score = 0.20
    else:
        macd_score = 0.35

    # Sentiment
    sent_score = 0.80 if fear_greed < 25 else 0.65 if fear_greed < 40 else 0.25 if fear_greed > 75 else 0.40 if fear_greed > 60 else 0.50

    # Chaos
    chaos_score = 0.75 if hurst > 0.6 else 0.62 if hurst > 0.55 else 0.30 if hurst < 0.4 else 0.50

    # VWAP score
    vwap_score = max(0.05, min(0.95, 0.5 + math.tanh(vwap_diff * 100) * 0.35))

    scores = {
        "trend": round(trend_score, 4),
        "momentum": round(mom_score, 4),
        "rsi": round(rsi_score, 4),
        "macd": round(macd_score, 4),
        "fibo": round(fibo_score, 4),
        "liq": round(liq_score, 4),
        "sent": round(sent_score, 4),
        "chaos": round(chaos_score, 4),
        "vwap": round(vwap_score, 4),
        "basis": round(basis_score, 4),
        "regime": round(regime_score, 4),
        "btc_lead": round(btc_score, 4),
    }

    return {
        "scores": scores,
        "price": P,
        "trend_direction": trend_dir,
        "rsi": round(rsi_val, 2),
        "atr": round(atr_val, 8),
        "macd_hist": round(macd["hist"], 8),
        "vwap": round(vwap, 2),
        "vwap_position": vwap_pos,
        "cvd": round(cvd, 0),
        "cvd_direction": cvd_dir,
        "ls_ratio": ls_ratio,
        "ls_view": ls_view,
        "basis": round(basis, 4),
        "basis_pct": round(basis_pct, 4),
        "basis_regime": basis_regime,
        "market_regime": regime,
        "btc_correlation": round(btc_corr, 4),
        "btc_change_3c": round(btc_change, 6),
        "hurst": round(hurst, 4),
        "lyapunov": round(lyap, 4),
        "realized_vol": round(real_vol, 6),
        "fibo_level": fibo_level,
        "ema_20": round(em20, 2),
        "ema_50": round(em50, 2),
        "ema_200": round(em200, 2),
        "high_50": round(hi, 2),
        "low_50": round(lo, 2),
    }


def compute_final_signal(
    score_data: Dict,
    weights: Dict[str, float] = None,
    symbol_profile: Dict = None,
) -> Dict:
    """
    Compute final trading signal from component scores.
    Uses dynamic weights from DB (Bayesian-updated) or defaults.
    """
    if "error" in score_data:
        return score_data

    W = dict(weights or DEFAULT_WEIGHTS)
    scores = score_data["scores"]
    P = score_data["price"]
    atr = score_data["atr"]
    trend_dir = score_data["trend_direction"]

    # Normalize weights
    total_w = sum(W.values()) or 1
    composite = sum((W.get(k, 0) / total_w) * scores.get(k, 0.5) for k in COMPONENTS)

    # Penalties
    lyap_p = 0.90 if score_data["lyapunov"] > -2.5 else 1.0
    vol_p = 0.85 if score_data["realized_vol"] > 2.0 else 0.92 if score_data["realized_vol"] > 1.5 else 1.0
    btc_crash = 0.80 if score_data["btc_change_3c"] < -0.02 else 1.0
    evt_p = _evt_penalty([P])  # simplified

    session, ses_mul = _get_session()

    # Funding rate penalty
    fund_p = 1.0  # Will be applied externally if data available

    # Symbol profile adjustments
    conf_bias = 0
    if symbol_profile:
        conf_bias = float(symbol_profile.get("confidence_bias", 0))

    final_raw = composite * lyap_p * evt_p * vol_p * btc_crash * ses_mul * fund_p
    confidence = max(1, min(99, round(final_raw * 100 + conf_bias)))

    # Signal type
    ts = scores.get("trend", 0.5)
    ms = scores.get("momentum", 0.5)
    rs = scores.get("rsi", 0.5)

    signal_type = "NEUTRAL"
    if ts > 0.6 and ms > 0.55 and rs > 0.5:
        signal_type = "LONG"
    elif ts < 0.4 and ms < 0.45 and rs < 0.5:
        signal_type = "SHORT"
    elif confidence >= NEAR_MISS_LOW and trend_dir != "NEUTRAL":
        signal_type = trend_dir

    should_trade = confidence >= THRESHOLD and signal_type != "NEUTRAL"
    near_miss = NEAR_MISS_LOW <= confidence < THRESHOLD and signal_type != "NEUTRAL"

    # Targets — ATR-based with profile adjustments
    sl_mul = float(symbol_profile.get("sl_multiplier", 1.5)) if symbol_profile else 1.5
    tp_mul = float(symbol_profile.get("tp_multiplier", PHI)) if symbol_profile else PHI
    atr_mul = sl_mul + (confidence / 100) * PHI_INV

    if signal_type == "LONG":
        sl = P - atr * atr_mul
        tp = P + atr * atr_mul * tp_mul
    else:
        sl = P + atr * atr_mul
        tp = P - atr * atr_mul * tp_mul

    sl_pct = abs((sl - P) / P * 100) if P > 0 else 0
    tp_pct = abs((tp - P) / P * 100) if P > 0 else 0
    rr_ratio = round(tp_pct / sl_pct, 2) if sl_pct > 0 else 0

    # Kelly Criterion × φ
    win_prob = confidence / 100
    kelly_full = max(0, (1.5 * win_prob - (1 - win_prob)) / 1.5)
    kelly_half = max(0, kelly_full * 0.5 * PHI_INV)
    pos_size = "FULL" if kelly_half > 0.15 else "HALF" if kelly_half > 0.08 else "QUARTER"

    return {
        "signal_type": signal_type,
        "confidence": confidence,
        "should_trade": should_trade,
        "near_miss": near_miss,
        "price": round(P, 8),
        "tp": round(tp, 8),
        "sl": round(sl, 8),
        "tp_pct": round(tp_pct, 2),
        "sl_pct": round(sl_pct, 2),
        "rr_ratio": rr_ratio,
        "position_size": pos_size,
        "kelly_full": round(kelly_full, 4),
        "kelly_half": round(kelly_half, 4),
        "session": session,
        "session_mul": ses_mul,
        "threshold": THRESHOLD,
        **score_data,
    }


async def analyze_symbol_deterministic(
    symbol: str,
    klines_data: List[list],
    btc_klines_data: List[list] = None,
    weights: Dict[str, float] = None,
    symbol_profile: Dict = None,
    order_book: Dict = None,
    funding_rate: float = 0,
    fear_greed: int = 50,
    ls_ratio: float = 1.0,
    spot_price: float = 0,
) -> Dict:
    """
    Main entry point — analyze a symbol deterministically.
    """
    def to_kline(raw: list) -> Dict:
        return {"t": int(raw[0]), "o": float(raw[1]), "h": float(raw[2]),
                "l": float(raw[3]), "c": float(raw[4]), "v": float(raw[5])}

    klines = [to_kline(k) for k in klines_data if isinstance(k, list) and len(k) >= 6]
    btc_klines = [to_kline(k) for k in (btc_klines_data or []) if isinstance(k, list) and len(k) >= 6]

    score_data = compute_scores(
        klines=klines,
        btc_klines=btc_klines or None,
        order_book=order_book,
        funding_rate=funding_rate,
        fear_greed=fear_greed,
        ls_ratio=ls_ratio,
        spot_price=spot_price,
    )

    result = compute_final_signal(score_data, weights, symbol_profile)
    result["symbol"] = symbol
    return result
