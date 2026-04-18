"use client";
import { useState, useEffect, useCallback } from "react";
import { paperApi } from "@/lib/api";

interface Signal {
  id: string; symbol: string; signal_type: string; timeframe_type: string;
  entry_price: number; target_1: number; target_2: number | null; target_3: number | null;
  stop_loss: number; confidence: number; reasoning: string; status: string;
  hit_target_level: number | null; technical_data: any;
  created_at: string; expires_at: string | null; closed_at: string | null;
}

const statusLabels: Record<string, { label: string; color: string; bg: string }> = {
  active: { label: "نشطة", color: "#3b82f6", bg: "rgba(59,130,246,0.08)" },
  hit_target: { label: "وصلت الهدف ✅", color: "#10b981", bg: "rgba(16,185,129,0.08)" },
  stopped: { label: "وقف خسارة ❌", color: "#ef4444", bg: "rgba(239,68,68,0.08)" },
  expired: { label: "منتهية", color: "#8e95ab", bg: "rgba(142,149,171,0.08)" },
};

function getRisk(signal: Signal): { label: string; color: string; bg: string; level: number } {
  const entryToStop = Math.abs(signal.entry_price - signal.stop_loss) / signal.entry_price * 100;
  const entryToTarget = Math.abs(signal.target_1 - signal.entry_price) / signal.entry_price * 100;
  const rr = entryToTarget / (entryToStop || 1); // Risk-Reward Ratio

  if (signal.confidence >= 75 && rr >= 2) return { label: "منخفضة", color: "#10b981", bg: "rgba(16,185,129,0.08)", level: 1 };
  if (signal.confidence >= 55 && rr >= 1.2) return { label: "متوسطة", color: "#f59e0b", bg: "rgba(245,158,11,0.08)", level: 2 };
  return { label: "عالية", color: "#ef4444", bg: "rgba(239,68,68,0.08)", level: 3 };
}

export default function SignalsPage() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [filter, setFilter] = useState<"all" | "active" | "short_term" | "long_term">("active");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [genResult, setGenResult] = useState("");

  const fetchSignals = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = {};
      if (filter === "active") params.status = "active";
      else if (filter === "short_term") params.timeframe_type = "short_term";
      else if (filter === "long_term") params.timeframe_type = "long_term";
      const { data } = await paperApi.getSignals(params);
      setSignals(data);
    } catch {} finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { fetchSignals(); }, [fetchSignals]);

  async function handleGenerate() {
    setGenerating(true); setGenResult("");
    try {
      const { data } = await paperApi.generateSignals();
      setGenResult(data.message);
      fetchSignals();
    } catch (e: any) {
      setGenResult("❌ " + (e.response?.data?.detail || "فشل التوليد"));
    } finally { setGenerating(false); }
  }

  return (
    <div style={{ padding: 32 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: "var(--text-primary)", marginBottom: 6 }}>🎯 التوصيات والإشارات</h1>
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>توصيات تداول مع أهداف ووقف خسارة — مبنية على التحليل الفني + Smart Money</p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
          <button className="btn btn-primary" onClick={handleGenerate} disabled={generating}
            style={{ fontSize: 13, padding: "10px 20px" }}>
            {generating ? "⏳ جارٍ التحليل..." : "🔄 تحديث التوصيات"}
          </button>
          {genResult && <span style={{ fontSize: 12, color: genResult.startsWith("❌") ? "#ef4444" : "#10b981" }}>{genResult}</span>}
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20, background: "var(--bg-secondary)", borderRadius: 10, padding: 4, maxWidth: 520 }}>
        {([
          { key: "active", label: "🟢 النشطة" },
          { key: "short_term", label: "⚡ قصيرة المدى" },
          { key: "long_term", label: "📈 طويلة المدى" },
          { key: "all", label: "📋 الكل" },
        ] as const).map(f => (
          <button key={f.key} onClick={() => setFilter(f.key)}
            style={{
              flex: 1, padding: "9px 0", borderRadius: 8, border: "none", cursor: "pointer", fontSize: 12, fontWeight: 600,
              background: filter === f.key ? "var(--bg-primary)" : "transparent",
              color: filter === f.key ? "var(--text-primary)" : "var(--text-muted)",
              boxShadow: filter === f.key ? "0 1px 4px rgba(0,0,0,0.06)" : "none",
            }}>
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: 60 }}><div className="spinner" /></div>
      ) : signals.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 60 }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🎯</div>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8, color: "var(--text-primary)" }}>لا توجد توصيات حالياً</div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 20 }}>اضغط "تحديث التوصيات" لتوليد توصيات جديدة بناءً على تحليل السوق الحالي</div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))", gap: 16 }}>
          {signals.map(s => {
            const st = statusLabels[s.status] || statusLabels.active;
            const isLong = s.signal_type === "long";
            const risk = getRisk(s);
            const entryToStop = Math.abs(s.entry_price - s.stop_loss) / s.entry_price * 100;
            const entryToT1 = Math.abs(s.target_1 - s.entry_price) / s.entry_price * 100;
            const rr = (entryToT1 / (entryToStop || 1)).toFixed(1);

            return (
              <div key={s.id} className="card" style={{ padding: 0, overflow: "hidden", border: s.status === "active" ? `1px solid ${isLong ? "rgba(16,185,129,0.2)" : "rgba(239,68,68,0.2)"}` : undefined }}>
                {/* Header */}
                <div style={{
                  padding: "16px 20px",
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  borderBottom: "1px solid var(--border)",
                  background: isLong ? "rgba(16,185,129,0.03)" : "rgba(239,68,68,0.03)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{
                      fontSize: 13, fontWeight: 800, padding: "6px 12px", borderRadius: 8,
                      background: isLong ? "rgba(16,185,129,0.12)" : "rgba(239,68,68,0.12)",
                      color: isLong ? "#10b981" : "#ef4444",
                    }}>
                      {isLong ? "📈 LONG" : "📉 SHORT"}
                    </div>
                    <div>
                      <div style={{ fontSize: 17, fontWeight: 800 }}>{s.symbol}</div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {s.timeframe_type === "short_term" ? "⚡ قصير المدى (24 ساعة)" : "📊 طويل المدى (7 أيام)"}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                    <span style={{ padding: "3px 10px", borderRadius: 6, fontSize: 11, fontWeight: 700, background: st.bg, color: st.color }}>{st.label}</span>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>ثقة: {s.confidence}%</span>
                  </div>
                </div>

                {/* Risk & RR */}
                <div style={{ padding: "12px 20px", display: "flex", gap: 10, borderBottom: "1px solid var(--border)" }}>
                  <div style={{ flex: 1, padding: "8px 12px", borderRadius: 8, background: risk.bg, border: `1px solid ${risk.color}22`, textAlign: "center" }}>
                    <div style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 600, marginBottom: 2 }}>⚠️ نسبة الخطورة</div>
                    <div style={{ fontSize: 14, fontWeight: 800, color: risk.color }}>{risk.label}</div>
                  </div>
                  <div style={{ flex: 1, padding: "8px 12px", borderRadius: 8, background: "var(--bg-secondary)", textAlign: "center" }}>
                    <div style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 600, marginBottom: 2 }}>📐 نسبة المخاطرة/الربح</div>
                    <div style={{ fontSize: 14, fontWeight: 800, color: parseFloat(rr) >= 2 ? "#10b981" : parseFloat(rr) >= 1 ? "#f59e0b" : "#ef4444" }}>1:{rr}</div>
                  </div>
                  <div style={{ flex: 1, padding: "8px 12px", borderRadius: 8, background: "var(--bg-secondary)", textAlign: "center" }}>
                    <div style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 600, marginBottom: 2 }}>📏 مسافة الوقف</div>
                    <div style={{ fontSize: 14, fontWeight: 800, color: "#ef4444" }}>{entryToStop.toFixed(1)}%</div>
                  </div>
                </div>

                {/* Entry & Stop */}
                <div style={{ padding: "14px 20px" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
                    <div style={{ padding: "10px 14px", borderRadius: 8, background: "rgba(59,130,246,0.04)", border: "1px solid var(--border)" }}>
                      <div style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 600, marginBottom: 4 }}>🎯 سعر الدخول</div>
                      <div style={{ fontSize: 15, fontWeight: 800 }}>${s.entry_price.toLocaleString(undefined, { maximumFractionDigits: 8 })}</div>
                    </div>
                    <div style={{ padding: "10px 14px", borderRadius: 8, background: "rgba(239,68,68,0.04)", border: "1px solid rgba(239,68,68,0.1)" }}>
                      <div style={{ fontSize: 10, color: "#ef4444", fontWeight: 600, marginBottom: 4 }}>🛑 وقف الخسارة</div>
                      <div style={{ fontSize: 15, fontWeight: 800, color: "#ef4444" }}>${s.stop_loss.toLocaleString(undefined, { maximumFractionDigits: 8 })}</div>
                    </div>
                  </div>

                  {/* Targets */}
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)", marginBottom: 8 }}>
                    {isLong ? "🎯 أهداف الصعود (Long)" : "🎯 أهداف الهبوط (Short)"}
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    {[
                      { label: "الهدف 1", value: s.target_1, level: 1 },
                      { label: "الهدف 2", value: s.target_2, level: 2 },
                      { label: "الهدف 3", value: s.target_3, level: 3 },
                    ].filter(t => t.value).map(t => {
                      const pct = Math.abs((t.value! - s.entry_price) / s.entry_price * 100);
                      const hit = (s.hit_target_level || 0) >= t.level;
                      return (
                        <div key={t.level} style={{
                          flex: 1, padding: "8px 10px", borderRadius: 8, textAlign: "center",
                          background: hit ? "rgba(16,185,129,0.08)" : "var(--bg-secondary)",
                          border: `1px solid ${hit ? "rgba(16,185,129,0.2)" : "var(--border)"}`,
                        }}>
                          <div style={{ fontSize: 10, color: hit ? "#10b981" : "var(--text-muted)", fontWeight: 600, marginBottom: 2 }}>
                            {hit ? "✅ " : ""}{t.label}
                          </div>
                          <div style={{ fontSize: 13, fontWeight: 700, color: hit ? "#10b981" : "var(--text-primary)" }}>
                            ${t.value!.toLocaleString(undefined, { maximumFractionDigits: 8 })}
                          </div>
                          <div style={{ fontSize: 10, color: isLong ? "#10b981" : "#ef4444", fontWeight: 600 }}>
                            {isLong ? "+" : "-"}{pct.toFixed(1)}%
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Reasoning */}
                <div style={{ padding: "0 20px 14px" }}>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600, marginBottom: 6 }}>📋 التحليل</div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.8, whiteSpace: "pre-wrap", background: "var(--bg-secondary)", padding: "10px 14px", borderRadius: 8, maxHeight: 120, overflowY: "auto" }}>
                    {s.reasoning}
                  </div>
                </div>

                {/* Footer */}
                <div style={{ padding: "10px 20px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)" }}>
                  <span>🕐 {new Date(s.created_at).toLocaleString("ar-SA")}</span>
                  {s.expires_at && <span>⏰ ينتهي: {new Date(s.expires_at).toLocaleString("ar-SA")}</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
