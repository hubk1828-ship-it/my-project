from app.services.smc_engine import SMCEngine
import numpy as np
np.random.seed(42)
n = 200
c = np.cumsum(np.random.randn(n)) + 100
h = c + np.abs(np.random.randn(n))
l = c - np.abs(np.random.randn(n))
o = c + np.random.randn(n) * 0.3
engine = SMCEngine()
r = engine.analyze(o.tolist(), h.tolist(), l.tolist(), c.tolist())
s = r.get_signal()
d = r.to_dict()
print(f"Decision: {s['decision']} | Confidence: {s['confidence']}")
print(f"Breaks: {len(r.structure_breaks)} | OB: {len(r.order_blocks)} | FVG: {len(r.fair_value_gaps)} | EQ: {len(r.equal_levels)}")
print(f"Trend: {d['trend']} | Internal: {d['internal_trend']}")
print(f"Strong High: {d['strong_high']}")
print(f"Equilibrium: {d['equilibrium']}")
print("OK")
