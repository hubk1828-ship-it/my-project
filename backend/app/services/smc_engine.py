"""
Smart Money Concepts (SMC) Engine
Ported from LuxAlgo's Pine Script to Python
Detects: BOS, CHoCH, Order Blocks, FVG, EQH/EQL, Swing Structure
"""
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import IntEnum


class Bias(IntEnum):
    BEARISH = -1
    NEUTRAL = 0
    BULLISH = 1


@dataclass
class SwingPoint:
    price: float
    index: int
    type: str  # 'HH','HL','LH','LL'


@dataclass
class StructureBreak:
    type: str        # 'BOS' or 'CHoCH'
    bias: int        # BULLISH or BEARISH
    level: float     # price level broken
    index: int       # bar index where break occurred
    swing_index: int # bar index of the swing point


@dataclass
class OrderBlock:
    high: float
    low: float
    index: int
    bias: int        # BULLISH or BEARISH
    mitigated: bool = False
    mitigation_index: Optional[int] = None


@dataclass
class FairValueGap:
    top: float
    bottom: float
    index: int
    bias: int
    mitigated: bool = False


@dataclass
class EqualLevel:
    price1: float
    price2: float
    index1: int
    index2: int
    type: str  # 'EQH' or 'EQL'


@dataclass
class SMCResult:
    trend: int = 0  # BULLISH or BEARISH
    internal_trend: int = 0
    swing_points: List[SwingPoint] = field(default_factory=list)
    structure_breaks: List[StructureBreak] = field(default_factory=list)
    order_blocks: List[OrderBlock] = field(default_factory=list)
    fair_value_gaps: List[FairValueGap] = field(default_factory=list)
    equal_levels: List[EqualLevel] = field(default_factory=list)
    strong_high: Optional[float] = None
    weak_high: Optional[float] = None
    strong_low: Optional[float] = None
    weak_low: Optional[float] = None
    premium_zone: Optional[Tuple[float, float]] = None
    discount_zone: Optional[Tuple[float, float]] = None
    equilibrium: Optional[float] = None

    def to_dict(self):
        return {
            "trend": "bullish" if self.trend == Bias.BULLISH else "bearish" if self.trend == Bias.BEARISH else "neutral",
            "internal_trend": "bullish" if self.internal_trend == Bias.BULLISH else "bearish" if self.internal_trend == Bias.BEARISH else "neutral",
            "swing_points": [{"price": s.price, "index": s.index, "type": s.type} for s in self.swing_points[-10:]],
            "structure_breaks": [{"type": s.type, "bias": "bullish" if s.bias == Bias.BULLISH else "bearish", "level": s.level, "index": s.index} for s in self.structure_breaks[-10:]],
            "order_blocks": [{"high": o.high, "low": o.low, "index": o.index, "bias": "bullish" if o.bias == Bias.BULLISH else "bearish", "mitigated": o.mitigated} for o in self.order_blocks if not o.mitigated][-5:],
            "fair_value_gaps": [{"top": f.top, "bottom": f.bottom, "index": f.index, "bias": "bullish" if f.bias == Bias.BULLISH else "bearish", "mitigated": f.mitigated} for f in self.fair_value_gaps if not f.mitigated][-5:],
            "equal_levels": [{"price": round((e.price1 + e.price2) / 2, 8), "type": e.type, "index1": e.index1, "index2": e.index2} for e in self.equal_levels[-5:]],
            "strong_high": self.strong_high,
            "weak_high": self.weak_high,
            "strong_low": self.strong_low,
            "weak_low": self.weak_low,
            "premium_zone": list(self.premium_zone) if self.premium_zone else None,
            "discount_zone": list(self.discount_zone) if self.discount_zone else None,
            "equilibrium": self.equilibrium,
        }

    def get_signal(self) -> dict:
        """Generate trading signal from SMC analysis"""
        signals = []
        score = 50  # neutral start

        # --- Trend alignment ---
        if self.trend == Bias.BULLISH:
            score += 10
            signals.append("✅ الاتجاه العام صاعد (Swing Structure)")
        elif self.trend == Bias.BEARISH:
            score -= 10
            signals.append("✅ الاتجاه العام هابط (Swing Structure)")

        if self.internal_trend == self.trend and self.trend != Bias.NEUTRAL:
            score += 5
            signals.append("✅ توافق الهيكل الداخلي مع الخارجي")

        # --- Recent structure breaks ---
        recent_breaks = self.structure_breaks[-3:] if self.structure_breaks else []
        for brk in recent_breaks:
            if brk.type == "CHoCH":
                score += 8 if brk.bias == Bias.BULLISH else -8
                signals.append(f"⚡ تغيّر اتجاه {'صاعد' if brk.bias == Bias.BULLISH else 'هابط'} (CHoCH) عند {brk.level}")
            elif brk.type == "BOS":
                score += 5 if brk.bias == Bias.BULLISH else -5
                signals.append(f"📊 كسر هيكلي {'صاعد' if brk.bias == Bias.BULLISH else 'هابط'} (BOS) عند {brk.level}")

        # --- Active order blocks ---
        active_obs = [o for o in self.order_blocks if not o.mitigated]
        bull_obs = [o for o in active_obs if o.bias == Bias.BULLISH]
        bear_obs = [o for o in active_obs if o.bias == Bias.BEARISH]

        if bull_obs:
            score += 4
            signals.append(f"🟢 {len(bull_obs)} بلوك طلب نشط (Order Block صاعد)")
        if bear_obs:
            score -= 4
            signals.append(f"🔴 {len(bear_obs)} بلوك عرض نشط (Order Block هابط)")

        # --- Fair Value Gaps ---
        active_fvg = [f for f in self.fair_value_gaps if not f.mitigated]
        bull_fvg = [f for f in active_fvg if f.bias == Bias.BULLISH]
        bear_fvg = [f for f in active_fvg if f.bias == Bias.BEARISH]

        if bull_fvg:
            score += 3
            signals.append(f"📗 {len(bull_fvg)} فجوة قيمة عادلة صاعدة (Bullish FVG)")
        if bear_fvg:
            score -= 3
            signals.append(f"📕 {len(bear_fvg)} فجوة قيمة عادلة هابطة (Bearish FVG)")

        # --- Equal levels (liquidity) ---
        for eq in self.equal_levels[-3:]:
            if eq.type == "EQH":
                signals.append(f"🔻 سيولة في الأعلى EQH عند {eq.price1:.2f}")
            else:
                signals.append(f"🔺 سيولة في الأسفل EQL عند {eq.price1:.2f}")

        # --- Premium/Discount ---
        if self.premium_zone and self.discount_zone and self.equilibrium:
            signals.append(f"📐 منطقة التوازن: {self.equilibrium:.2f}")

        # --- Strong/Weak levels ---
        if self.strong_high:
            signals.append(f"💪 قمة قوية: {self.strong_high:.2f}")
        if self.weak_high:
            signals.append(f"⚠️ قمة ضعيفة: {self.weak_high:.2f}")
        if self.strong_low:
            signals.append(f"💪 قاع قوي: {self.strong_low:.2f}")
        if self.weak_low:
            signals.append(f"⚠️ قاع ضعيف: {self.weak_low:.2f}")

        # Clamp
        score = max(0, min(100, score))

        if score >= 65:
            decision = "buy"
        elif score <= 35:
            decision = "sell"
        else:
            decision = "no_opportunity"

        return {
            "decision": decision,
            "confidence": score,
            "signals": signals,
            "reasoning": "\n".join(signals),
        }


class SMCEngine:
    """
    Smart Money Concepts analyzer.
    Feed it OHLCV data and get back structure, order blocks, FVG, etc.
    """

    def __init__(self, swing_length: int = 50, internal_length: int = 5,
                 eqhl_length: int = 3, eqhl_threshold: float = 0.1,
                 ob_filter: str = "atr"):
        self.swing_length = swing_length
        self.internal_length = internal_length
        self.eqhl_length = eqhl_length
        self.eqhl_threshold = eqhl_threshold
        self.ob_filter = ob_filter

    def analyze(self, opens: list, highs: list, lows: list, closes: list,
                volumes: list = None) -> SMCResult:
        """
        Run full SMC analysis on OHLCV data.
        Returns SMCResult with all detected structures.
        """
        n = len(closes)
        if n < self.swing_length + 5:
            return SMCResult()

        o = np.array(opens, dtype=float)
        h = np.array(highs, dtype=float)
        l = np.array(lows, dtype=float)
        c = np.array(closes, dtype=float)

        result = SMCResult()

        # ATR for volatility filter
        tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
        tr = np.insert(tr, 0, h[0] - l[0])
        atr = self._rolling_mean(tr, min(200, n))

        # --- Swing Structure ---
        swing_highs, swing_lows = self._detect_pivots(h, l, self.swing_length)
        internal_highs, internal_lows = self._detect_pivots(h, l, self.internal_length)

        # --- Swing Points & Labels ---
        result.swing_points = self._label_swing_points(swing_highs, swing_lows)

        # --- Structure Breaks (BOS/CHoCH) ---
        swing_breaks, swing_trend = self._detect_structure_breaks(c, swing_highs, swing_lows)
        internal_breaks, internal_trend = self._detect_structure_breaks(c, internal_highs, internal_lows)

        result.structure_breaks = internal_breaks + swing_breaks
        result.trend = swing_trend
        result.internal_trend = internal_trend

        # --- Order Blocks ---
        result.order_blocks = self._detect_order_blocks(h, l, c, swing_breaks + internal_breaks, atr, n)
        self._mitigate_order_blocks(result.order_blocks, h, l, c)

        # --- Fair Value Gaps ---
        result.fair_value_gaps = self._detect_fvg(h, l, c, atr)
        self._mitigate_fvg(result.fair_value_gaps, h, l)

        # --- Equal Highs/Lows ---
        eqh_pivots, eql_pivots = self._detect_pivots(h, l, self.eqhl_length)
        result.equal_levels = self._detect_equal_levels(eqh_pivots, eql_pivots, atr)

        # --- Strong/Weak High/Low & Zones ---
        if swing_highs and swing_lows:
            trailing_high = max(h)
            trailing_low = min(l)

            if swing_trend == Bias.BEARISH:
                result.strong_high = trailing_high
                result.weak_low = trailing_low
            else:
                result.weak_high = trailing_high
                result.strong_low = trailing_low

            equilibrium = (trailing_high + trailing_low) / 2
            result.equilibrium = equilibrium
            result.premium_zone = (0.95 * trailing_high + 0.05 * trailing_low, trailing_high)
            result.discount_zone = (trailing_low, 0.95 * trailing_low + 0.05 * trailing_high)

        return result

    def _rolling_mean(self, data: np.ndarray, window: int) -> np.ndarray:
        """Compute rolling mean with edge padding"""
        result = np.full_like(data, np.nan)
        cumsum = np.cumsum(data)
        for i in range(len(data)):
            w = min(i + 1, window)
            if i < window:
                result[i] = cumsum[i] / (i + 1)
            else:
                result[i] = (cumsum[i] - cumsum[i - window]) / window
        return result

    def _detect_pivots(self, highs: np.ndarray, lows: np.ndarray, length: int) -> Tuple[list, list]:
        """Detect pivot highs and lows"""
        n = len(highs)
        pivot_highs = []  # (index, price)
        pivot_lows = []

        for i in range(length, n - length):
            # Pivot high: h[i] is highest in range
            if highs[i] == max(highs[i - length:i + length + 1]):
                pivot_highs.append((i, highs[i]))
            # Pivot low: l[i] is lowest in range
            if lows[i] == min(lows[i - length:i + length + 1]):
                pivot_lows.append((i, lows[i]))

        return pivot_highs, pivot_lows

    def _label_swing_points(self, swing_highs, swing_lows) -> List[SwingPoint]:
        """Label swing points as HH, HL, LH, LL"""
        points = []
        last_high = None
        last_low = None

        all_pivots = [(idx, price, 'high') for idx, price in swing_highs] + \
                     [(idx, price, 'low') for idx, price in swing_lows]
        all_pivots.sort(key=lambda x: x[0])

        for idx, price, ptype in all_pivots:
            if ptype == 'high':
                if last_high is None:
                    label = 'HH'
                elif price > last_high:
                    label = 'HH'
                else:
                    label = 'LH'
                last_high = price
                points.append(SwingPoint(price=price, index=idx, type=label))
            else:
                if last_low is None:
                    label = 'HL'
                elif price > last_low:
                    label = 'HL'
                else:
                    label = 'LL'
                last_low = price
                points.append(SwingPoint(price=price, index=idx, type=label))

        return points

    def _detect_structure_breaks(self, closes: np.ndarray, pivot_highs: list,
                                  pivot_lows: list) -> Tuple[List[StructureBreak], int]:
        """Detect BOS and CHoCH"""
        breaks = []
        trend = Bias.NEUTRAL

        # Track current structure levels
        current_high = None  # (index, price)
        current_low = None
        high_crossed = False
        low_crossed = False

        # Merge pivots chronologically
        all_pivots = [(idx, price, 'high') for idx, price in pivot_highs] + \
                     [(idx, price, 'low') for idx, price in pivot_lows]
        all_pivots.sort(key=lambda x: x[0])

        for idx, price, ptype in all_pivots:
            if ptype == 'high':
                current_high = (idx, price)
                high_crossed = False
            else:
                current_low = (idx, price)
                low_crossed = False

        # Now scan through closes for crossovers
        if not pivot_highs or not pivot_lows:
            return breaks, trend

        # Build a timeline of active swing levels
        high_levels = []  # (start_index, price, pivot_index)
        low_levels = []

        for i, (idx, price) in enumerate(pivot_highs):
            next_idx = pivot_highs[i + 1][0] if i + 1 < len(pivot_highs) else len(closes)
            high_levels.append((idx, next_idx, price))

        for i, (idx, price) in enumerate(pivot_lows):
            next_idx = pivot_lows[i + 1][0] if i + 1 < len(pivot_lows) else len(closes)
            low_levels.append((idx, next_idx, price))

        # Track breaks
        hi_idx = 0
        lo_idx = 0
        current_high_price = pivot_highs[0][1] if pivot_highs else None
        current_high_bar = pivot_highs[0][0] if pivot_highs else 0
        current_low_price = pivot_lows[0][1] if pivot_lows else None
        current_low_bar = pivot_lows[0][0] if pivot_lows else 0
        high_broken = False
        low_broken = False

        for bar in range(max(pivot_highs[0][0], pivot_lows[0][0]) if pivot_highs and pivot_lows else 0, len(closes)):
            # Update pivot levels
            while hi_idx < len(pivot_highs) - 1 and pivot_highs[hi_idx + 1][0] <= bar:
                hi_idx += 1
                current_high_price = pivot_highs[hi_idx][1]
                current_high_bar = pivot_highs[hi_idx][0]
                high_broken = False

            while lo_idx < len(pivot_lows) - 1 and pivot_lows[lo_idx + 1][0] <= bar:
                lo_idx += 1
                current_low_price = pivot_lows[lo_idx][1]
                current_low_bar = pivot_lows[lo_idx][0]
                low_broken = False

            if current_high_price is None or current_low_price is None:
                continue

            # Bullish break: close crosses above swing high
            if closes[bar] > current_high_price and not high_broken:
                tag = "CHoCH" if trend == Bias.BEARISH else "BOS"
                breaks.append(StructureBreak(
                    type=tag, bias=Bias.BULLISH,
                    level=current_high_price, index=bar,
                    swing_index=current_high_bar
                ))
                trend = Bias.BULLISH
                high_broken = True

            # Bearish break: close crosses below swing low
            if closes[bar] < current_low_price and not low_broken:
                tag = "CHoCH" if trend == Bias.BULLISH else "BOS"
                breaks.append(StructureBreak(
                    type=tag, bias=Bias.BEARISH,
                    level=current_low_price, index=bar,
                    swing_index=current_low_bar
                ))
                trend = Bias.BEARISH
                low_broken = True

        return breaks, trend

    def _detect_order_blocks(self, highs, lows, closes, breaks, atr, n) -> List[OrderBlock]:
        """Detect order blocks at structure break points"""
        obs = []
        vol_measure = atr

        for brk in breaks:
            si = brk.swing_index
            bi = brk.index

            if si >= bi or si < 0 or bi >= n:
                continue

            if brk.bias == Bias.BULLISH:
                # Find the lowest low candle in the range before the break
                segment_lows = lows[si:bi]
                if len(segment_lows) == 0:
                    continue
                min_idx = si + int(np.argmin(segment_lows))

                # Filter by volatility
                candle_range = highs[min_idx] - lows[min_idx]
                if candle_range < 2 * vol_measure[min_idx] if min_idx < len(vol_measure) else True:
                    obs.append(OrderBlock(
                        high=float(highs[min_idx]),
                        low=float(lows[min_idx]),
                        index=min_idx,
                        bias=Bias.BULLISH,
                    ))
            else:
                # Find the highest high candle
                segment_highs = highs[si:bi]
                if len(segment_highs) == 0:
                    continue
                max_idx = si + int(np.argmax(segment_highs))

                candle_range = highs[max_idx] - lows[max_idx]
                if candle_range < 2 * vol_measure[max_idx] if max_idx < len(vol_measure) else True:
                    obs.append(OrderBlock(
                        high=float(highs[max_idx]),
                        low=float(lows[max_idx]),
                        index=max_idx,
                        bias=Bias.BEARISH,
                    ))

        return obs

    def _mitigate_order_blocks(self, obs: List[OrderBlock], highs, lows, closes):
        """Mark mitigated order blocks"""
        for ob in obs:
            for i in range(ob.index + 1, len(closes)):
                if ob.bias == Bias.BEARISH and highs[i] > ob.high:
                    ob.mitigated = True
                    ob.mitigation_index = i
                    break
                elif ob.bias == Bias.BULLISH and lows[i] < ob.low:
                    ob.mitigated = True
                    ob.mitigation_index = i
                    break

    def _detect_fvg(self, highs, lows, closes, atr) -> List[FairValueGap]:
        """Detect Fair Value Gaps"""
        fvgs = []
        n = len(closes)

        for i in range(2, n):
            # Bullish FVG: current low > 2-bars-ago high
            if lows[i] > highs[i - 2]:
                gap_size = lows[i] - highs[i - 2]
                if gap_size > 0:
                    fvgs.append(FairValueGap(
                        top=float(lows[i]),
                        bottom=float(highs[i - 2]),
                        index=i - 1,
                        bias=Bias.BULLISH,
                    ))
            # Bearish FVG: current high < 2-bars-ago low
            elif highs[i] < lows[i - 2]:
                gap_size = lows[i - 2] - highs[i]
                if gap_size > 0:
                    fvgs.append(FairValueGap(
                        top=float(lows[i - 2]),
                        bottom=float(highs[i]),
                        index=i - 1,
                        bias=Bias.BEARISH,
                    ))

        return fvgs

    def _mitigate_fvg(self, fvgs: List[FairValueGap], highs, lows):
        """Mark mitigated FVGs"""
        for fvg in fvgs:
            for i in range(fvg.index + 1, len(highs)):
                if fvg.bias == Bias.BULLISH and lows[i] < fvg.bottom:
                    fvg.mitigated = True
                    break
                elif fvg.bias == Bias.BEARISH and highs[i] > fvg.top:
                    fvg.mitigated = True
                    break

    def _detect_equal_levels(self, pivot_highs, pivot_lows, atr) -> List[EqualLevel]:
        """Detect Equal Highs and Equal Lows"""
        equals = []

        # Equal Highs
        for i in range(1, len(pivot_highs)):
            idx1, p1 = pivot_highs[i - 1]
            idx2, p2 = pivot_highs[i]
            threshold = self.eqhl_threshold * atr[min(idx2, len(atr) - 1)]
            if abs(p1 - p2) < threshold:
                equals.append(EqualLevel(
                    price1=p1, price2=p2,
                    index1=idx1, index2=idx2,
                    type="EQH"
                ))

        # Equal Lows
        for i in range(1, len(pivot_lows)):
            idx1, p1 = pivot_lows[i - 1]
            idx2, p2 = pivot_lows[i]
            threshold = self.eqhl_threshold * atr[min(idx2, len(atr) - 1)]
            if abs(p1 - p2) < threshold:
                equals.append(EqualLevel(
                    price1=p1, price2=p2,
                    index1=idx1, index2=idx2,
                    type="EQL"
                ))

        return equals
