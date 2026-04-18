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
  hit_target: { label: "وصلت الهدف", color: "#10b981", bg: "rgba(16,185,129,0.08)" },
  stopped: { label: "وقف خسارة", color: "#ef4444", bg: "rgba(239,68,68,0.08)" },
  expired: { label: "منتهية", color: "#8e95ab", bg: "rgba(142,149,171,0.08)" },
};

export default function SignalsPage() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [filter, setFilter] = useState<"all" | "active" | "short_term" | "long_term">("active");
  const [loading, setLoading] = useState(true);

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

  return (
    <div style={{ padding: 32 }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: "var(--text-primary)", marginBottom: 6 }}>🎯 التوصيات والإشارات</h1>
        <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>توصيات تداول مع أهداف ووقف خسارة — مبنية على التحليل الفني + Smart Money</p>
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
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>سيتم تحديث التوصيات تلقائياً كل ساعتين بناءً على تحليل السوق</div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: 16 }}>
          {signals.map(s => {
            const st = statusLabels[s.status] || statusLabels.active;
            const isLong = s.signal_type === "long";
            const priceDiff = s.status === "active" ? null : s.hit_target_level
              ? ((isLong ? (s[`target_${s.hit_target_level}` as keyof Signal] as number) : s.entry_price) - (isLong ? s.entry_price : (s[`target_${s.hit_target_level}` as keyof Signal] as number))) / s.entry_price * 100
              : (s.stop_loss - s.entry_price) / s.entry_price * 100 * (isLong ? 1 : -1);

            return (
              <div key={s.id} className="card" style={{ padding: 0, overflow: "hidden" }}>
                {/* Header */}
                <div style={{ padding: "16px 20px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontSize: 22, padding: "6px 10px", borderRadius: 10, background: isLong ? "rgba(16,185,129,0.08)" : "rgba(239,68,68,0.08)" }}>
                      {isLong ? "📈" : "📉"}
                    </span>
                    <div>
                      <div style={{ fontSize: 16, fontWeight: 800 }}>{s.symbol}</div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {isLong ? "شراء (Long)" : "بيع (Short)"} • {s.timeframe_type === "short_term" ? "قصير المدى" : "طويل المدى"}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                    <span style={{ padding: "3px 10px", borderRadius: 6, fontSize: 11, fontWeight: 700, background: st.bg, color: st.color }}>{st.label}</span>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>ثقة: {s.confidence}%</span>
                  </div>
                </div>

                {/* Targets */}
                <div style={{ padding: "16px 20px" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 14 }}>
                    <div style={{ padding: "10px 14px", borderRadius: 8, background: "rgba(59,130,246,0.04)", border: "1px solid var(--border)" }}>
                      <div style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 600, marginBottom: 4 }}>سعر الدخول</div>
                      <div style={{ fontSize: 15, fontWeight: 800 }}>${s.entry_price.toLocaleString(undefined, { maximumFractionDigits: 8 })}</div>
                    </div>
                    <div style={{ padding: "10px 14px", borderRadius: 8, background: "rgba(239,68,68,0.04)", border: "1px solid rgba(239,68,68,0.1)" }}>
                      <div style={{ fontSize: 10, color: "#ef4444", fontWeight: 600, marginBottom: 4 }}>وقف الخسارة</div>
                      <div style={{ fontSize: 15, fontWeight: 800, color: "#ef4444" }}>${s.stop_loss.toLocaleString(undefined, { maximumFractionDigits: 8 })}</div>
                    </div>
                  </div>

                  {/* Target levels */}
                  <div style={{ display: "flex", gap: 8 }}>
                    {[
                      { label: "الهدف 1", value: s.target_1, level: 1 },
                      { label: "الهدف 2", value: s.target_2, level: 2 },
                      { label: "الهدف 3", value: s.target_3, level: 3 },
                    ].filter(t => t.value).map(t => (
                      <div key={t.level} style={{
                        flex: 1, padding: "8px 10px", borderRadius: 8, textAlign: "center",
                        background: (s.hit_target_level || 0) >= t.level ? "rgba(16,185,129,0.08)" : "var(--bg-secondary)",
                        border: `1px solid ${(s.hit_target_level || 0) >= t.level ? "rgba(16,185,129,0.2)" : "var(--border)"}`,
                      }}>
                        <div style={{ fontSize: 10, color: (s.hit_target_level || 0) >= t.level ? "#10b981" : "var(--text-muted)", fontWeight: 600, marginBottom: 2 }}>
                          {(s.hit_target_level || 0) >= t.level ? "✅ " : ""}{t.label}
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: (s.hit_target_level || 0) >= t.level ? "#10b981" : "var(--text-primary)" }}>
                          ${t.value!.toLocaleString(undefined, { maximumFractionDigits: 8 })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Reasoning */}
                <div style={{ padding: "0 20px 16px" }}>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600, marginBottom: 6 }}>التحليل</div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.8, whiteSpace: "pre-wrap", background: "var(--bg-secondary)", padding: "10px 14px", borderRadius: 8, maxHeight: 120, overflowY: "auto" }}>
                    {s.reasoning}
                  </div>
                </div>

                {/* Footer */}
                <div style={{ padding: "10px 20px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)" }}>
                  <span>{new Date(s.created_at).toLocaleString("ar-SA")}</span>
                  {s.expires_at && <span>ينتهي: {new Date(s.expires_at).toLocaleString("ar-SA")}</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
