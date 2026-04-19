"use client";
import { useState, useEffect, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { paperApi } from "@/lib/api";

interface Signal {
  id: string; symbol: string; signal_type: string; timeframe_type: string;
  entry_price: number; target_1: number; target_2: number | null; target_3: number | null;
  stop_loss: number; confidence: number; reasoning: string; status: string;
  hit_target_level: number | null; technical_data: any;
  created_at: string; expires_at: string | null; closed_at: string | null;
  pnl_pct?: number;
}

interface Performance {
  total: number; success: number; stopped: number; expired: number;
  success_rate: number; loss_rate: number; avg_pnl_pct: number; total_pnl_pct: number;
}

interface BotAnalysis {
  analysis: string; issues: string[]; recommendations: string[];
  success_rate?: number; loss_rate?: number; total_analyzed?: number;
}

const statusLabels: Record<string, { label: string; color: string; bg: string }> = {
  active: { label: "نشطة", color: "#3b82f6", bg: "rgba(59,130,246,0.08)" },
  hit_target: { label: "وصلت الهدف ✅", color: "#10b981", bg: "rgba(16,185,129,0.08)" },
  stopped: { label: "وقف خسارة ❌", color: "#ef4444", bg: "rgba(239,68,68,0.08)" },
  expired: { label: "منتهية", color: "#8e95ab", bg: "rgba(142,149,171,0.08)" },
};

function getRisk(s: Signal) {
  const entryToStop = Math.abs(s.entry_price - s.stop_loss) / s.entry_price * 100;
  const entryToT1 = Math.abs(s.target_1 - s.entry_price) / s.entry_price * 100;
  const rr = entryToT1 / (entryToStop || 1);
  if (s.confidence >= 75 && rr >= 2) return { label: "منخفضة", color: "#10b981", bg: "rgba(16,185,129,0.08)" };
  if (s.confidence >= 55 && rr >= 1.2) return { label: "متوسطة", color: "#f59e0b", bg: "rgba(245,158,11,0.08)" };
  return { label: "عالية", color: "#ef4444", bg: "rgba(239,68,68,0.08)" };
}

function timeLeft(expiresAt: string | null) {
  if (!expiresAt) return "";
  const diff = new Date(expiresAt).getTime() - Date.now();
  if (diff <= 0) return "منتهية";
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  return h > 24 ? `${Math.floor(h / 24)}d ${h % 24}h` : `${h}h ${m}m`;
}

function SignalsPageContent() {
  const searchParams = useSearchParams();
  const symbolParam = searchParams.get("symbol");

  const [signals, setSignals] = useState<Signal[]>([]);
  const [filter, setFilter] = useState<"all" | "active" | "short_term" | "long_term">("active");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [genResult, setGenResult] = useState("");
  const [timeframe, setTimeframe] = useState("1h");
  const [activeTab, setActiveTab] = useState<"signals" | "performance" | "bot">("signals");
  const [performance, setPerformance] = useState<Performance | null>(null);
  const [botAnalysis, setBotAnalysis] = useState<BotAnalysis | null>(null);
  const [perfLoading, setPerfLoading] = useState(false);

  const timeframes = [
    { value: "1m", label: "1 دقيقة" }, { value: "5m", label: "5 دقائق" },
    { value: "15m", label: "15 دقيقة" }, { value: "30m", label: "30 دقيقة" },
    { value: "1h", label: "1 ساعة" }, { value: "4h", label: "4 ساعات" },
    { value: "1d", label: "يومي" }, { value: "1w", label: "أسبوعي" },
  ];

  const fetchSignals = useCallback(async () => {
    setLoading(true);
    try {
      if (symbolParam) {
        const { data } = await paperApi.getSignalHistory(symbolParam);
        setSignals(data);
      } else {
        const params: any = {};
        if (filter === "active") params.status = "active";
        else if (filter === "short_term") params.timeframe_type = "short_term";
        else if (filter === "long_term") params.timeframe_type = "long_term";
        const { data } = await paperApi.getSignals(params);
        setSignals(data);
      }
    } catch {} finally { setLoading(false); }
  }, [filter, symbolParam]);

  useEffect(() => { fetchSignals(); }, [fetchSignals]);

  async function handleGenerate() {
    setGenerating(true); setGenResult("");
    try {
      const { data } = await paperApi.generateSignals(timeframe);
      setGenResult(data.message);
      fetchSignals();
    } catch (e: any) {
      setGenResult("❌ " + (e.response?.data?.detail || "فشل التوليد"));
    } finally { setGenerating(false); }
  }

  async function loadPerformance() {
    setPerfLoading(true);
    try {
      const [pRes, bRes] = await Promise.allSettled([
        paperApi.getSignalPerformance(symbolParam || undefined),
        paperApi.getBotAnalysis(),
      ]);
      if (pRes.status === "fulfilled") setPerformance(pRes.value.data);
      if (bRes.status === "fulfilled") setBotAnalysis(bRes.value.data);
    } catch {} finally { setPerfLoading(false); }
  }

  useEffect(() => { if (activeTab === "performance" || activeTab === "bot") loadPerformance(); }, [activeTab]);

  return (
    <div style={{ padding: 32 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: "var(--text-primary)", marginBottom: 6 }}>
            🎯 {symbolParam ? `توصيات ${symbolParam}` : "التوصيات والإشارات"}
          </h1>
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>
            {symbolParam ? `سجل التوصيات لعملة ${symbolParam}` : "توصيات تداول بأهداف قريبة مضمونة — مبنية على التحليل الفني + SMC"}
          </p>
          {symbolParam && <a href="/signals" style={{ fontSize: 12, color: "var(--accent-blue)" }}>← عودة لكل التوصيات</a>}
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select className="form-input" value={timeframe} onChange={e => setTimeframe(e.target.value)}
              style={{ padding: "8px 12px", fontSize: 13, minWidth: 120 }}>
              {timeframes.map(tf => <option key={tf.value} value={tf.value}>{tf.label}</option>)}
            </select>
            <button className="btn btn-primary" onClick={handleGenerate} disabled={generating}
              style={{ fontSize: 13, padding: "10px 20px", whiteSpace: "nowrap" }}>
              {generating ? "⏳ جارٍ التحليل..." : "🔄 تحديث التوصيات"}
            </button>
          </div>
          {genResult && <span style={{ fontSize: 12, color: genResult.startsWith("❌") ? "#ef4444" : "#10b981" }}>{genResult}</span>}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20, background: "var(--bg-secondary)", borderRadius: 10, padding: 4, maxWidth: 480 }}>
        {([
          { key: "signals", label: "📋 التوصيات" },
          { key: "performance", label: "📊 الأداء" },
          { key: "bot", label: "🧠 تحليل البوت" },
        ] as const).map(t => (
          <button key={t.key} onClick={() => setActiveTab(t.key)}
            style={{
              flex: 1, padding: "9px 0", borderRadius: 8, border: "none", cursor: "pointer", fontSize: 12, fontWeight: 600,
              background: activeTab === t.key ? "var(--bg-primary)" : "transparent",
              color: activeTab === t.key ? "var(--text-primary)" : "var(--text-muted)",
              boxShadow: activeTab === t.key ? "0 1px 4px rgba(0,0,0,0.06)" : "none",
            }}>{t.label}</button>
        ))}
      </div>

      {/* SIGNALS TAB */}
      {activeTab === "signals" && (
        <>
          {!symbolParam && (
            <div style={{ display: "flex", gap: 4, marginBottom: 20, background: "var(--bg-secondary)", borderRadius: 10, padding: 4, maxWidth: 520 }}>
              {([
                { key: "active", label: "🟢 النشطة" },
                { key: "short_term", label: "⚡ قصيرة" },
                { key: "long_term", label: "📈 طويلة" },
                { key: "all", label: "📋 الكل" },
              ] as const).map(f => (
                <button key={f.key} onClick={() => setFilter(f.key)}
                  style={{
                    flex: 1, padding: "9px 0", borderRadius: 8, border: "none", cursor: "pointer", fontSize: 12, fontWeight: 600,
                    background: filter === f.key ? "var(--bg-primary)" : "transparent",
                    color: filter === f.key ? "var(--text-primary)" : "var(--text-muted)",
                    boxShadow: filter === f.key ? "0 1px 4px rgba(0,0,0,0.06)" : "none",
                  }}>{f.label}</button>
              ))}
            </div>
          )}

          {loading ? <div style={{ textAlign: "center", padding: 60 }}><div className="spinner" /></div> :
          signals.length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: 60 }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>🎯</div>
              <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>لا توجد توصيات</div>
              <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 20 }}>اضغط "تحديث التوصيات" لتوليد توصيات جديدة</div>
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
                const remaining = s.status === "active" ? timeLeft(s.expires_at) : "";
                const duration = s.technical_data?.duration_hours;

                return (
                  <div key={s.id} className="card" style={{ padding: 0, overflow: "hidden", border: s.status === "active" ? `1px solid ${isLong ? "rgba(16,185,129,0.2)" : "rgba(239,68,68,0.2)"}` : undefined }}>
                    <div style={{ padding: "14px 20px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border)", background: isLong ? "rgba(16,185,129,0.03)" : "rgba(239,68,68,0.03)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div style={{ fontSize: 13, fontWeight: 800, padding: "5px 10px", borderRadius: 8, background: isLong ? "rgba(16,185,129,0.12)" : "rgba(239,68,68,0.12)", color: isLong ? "#10b981" : "#ef4444" }}>
                          {isLong ? "📈 LONG" : "📉 SHORT"}
                        </div>
                        <div>
                          <div style={{ fontSize: 16, fontWeight: 800 }}>{s.symbol}</div>
                          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                            {s.timeframe_type === "short_term" ? "⚡ قصير المدى" : "📊 طويل المدى"}
                            {duration ? ` • ${duration}h` : ""}
                          </div>
                        </div>
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                        <span style={{ padding: "3px 10px", borderRadius: 6, fontSize: 11, fontWeight: 700, background: st.bg, color: st.color }}>{st.label}</span>
                        {remaining && <span style={{ fontSize: 10, color: "var(--text-muted)" }}>⏳ {remaining}</span>}
                        {s.pnl_pct !== undefined && s.pnl_pct !== 0 && (
                          <span style={{ fontSize: 11, fontWeight: 700, color: s.pnl_pct > 0 ? "#10b981" : "#ef4444" }}>
                            {s.pnl_pct > 0 ? "+" : ""}{s.pnl_pct}%
                          </span>
                        )}
                      </div>
                    </div>

                    <div style={{ padding: "10px 20px", display: "flex", gap: 8, borderBottom: "1px solid var(--border)" }}>
                      <div style={{ flex: 1, padding: "6px 10px", borderRadius: 8, background: risk.bg, textAlign: "center" }}>
                        <div style={{ fontSize: 9, color: "var(--text-muted)", fontWeight: 600 }}>⚠️ الخطورة</div>
                        <div style={{ fontSize: 13, fontWeight: 800, color: risk.color }}>{risk.label}</div>
                      </div>
                      <div style={{ flex: 1, padding: "6px 10px", borderRadius: 8, background: "var(--bg-secondary)", textAlign: "center" }}>
                        <div style={{ fontSize: 9, color: "var(--text-muted)", fontWeight: 600 }}>📐 RR</div>
                        <div style={{ fontSize: 13, fontWeight: 800, color: parseFloat(rr) >= 2 ? "#10b981" : "#f59e0b" }}>1:{rr}</div>
                      </div>
                      <div style={{ flex: 1, padding: "6px 10px", borderRadius: 8, background: "var(--bg-secondary)", textAlign: "center" }}>
                        <div style={{ fontSize: 9, color: "var(--text-muted)", fontWeight: 600 }}>🎯 ثقة</div>
                        <div style={{ fontSize: 13, fontWeight: 800 }}>{s.confidence}%</div>
                      </div>
                    </div>

                    <div style={{ padding: "12px 20px" }}>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 10 }}>
                        <div style={{ padding: "8px 12px", borderRadius: 8, background: "rgba(59,130,246,0.04)", border: "1px solid var(--border)" }}>
                          <div style={{ fontSize: 9, color: "var(--text-muted)", fontWeight: 600 }}>🎯 الدخول</div>
                          <div style={{ fontSize: 14, fontWeight: 800 }}>${s.entry_price.toLocaleString(undefined, { maximumFractionDigits: 6 })}</div>
                        </div>
                        <div style={{ padding: "8px 12px", borderRadius: 8, background: "rgba(239,68,68,0.04)", border: "1px solid rgba(239,68,68,0.1)" }}>
                          <div style={{ fontSize: 9, color: "#ef4444", fontWeight: 600 }}>🛑 الوقف</div>
                          <div style={{ fontSize: 14, fontWeight: 800, color: "#ef4444" }}>${s.stop_loss.toLocaleString(undefined, { maximumFractionDigits: 6 })}</div>
                        </div>
                      </div>
                      <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", marginBottom: 6 }}>
                        {isLong ? "🎯 أهداف الصعود (Long)" : "🎯 أهداف الهبوط (Short)"}
                      </div>
                      <div style={{ display: "flex", gap: 6 }}>
                        {[{ label: "1", val: s.target_1, l: 1 }, { label: "2", val: s.target_2, l: 2 }, { label: "3", val: s.target_3, l: 3 }]
                          .filter(t => t.val).map(t => {
                            const p = Math.abs((t.val! - s.entry_price) / s.entry_price * 100);
                            const hit = (s.hit_target_level || 0) >= t.l;
                            return (
                              <div key={t.l} style={{ flex: 1, padding: "6px 8px", borderRadius: 8, textAlign: "center", background: hit ? "rgba(16,185,129,0.08)" : "var(--bg-secondary)", border: `1px solid ${hit ? "rgba(16,185,129,0.2)" : "var(--border)"}` }}>
                                <div style={{ fontSize: 9, color: hit ? "#10b981" : "var(--text-muted)", fontWeight: 600 }}>{hit ? "✅ " : ""}هدف {t.label}</div>
                                <div style={{ fontSize: 12, fontWeight: 700, color: hit ? "#10b981" : "var(--text-primary)" }}>${t.val!.toLocaleString(undefined, { maximumFractionDigits: 6 })}</div>
                                <div style={{ fontSize: 9, color: isLong ? "#10b981" : "#ef4444", fontWeight: 600 }}>{isLong ? "+" : "-"}{p.toFixed(1)}%</div>
                              </div>
                            );
                          })}
                      </div>
                    </div>
                    <div style={{ padding: "8px 20px 12px" }}>
                      <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.7, whiteSpace: "pre-wrap", background: "var(--bg-secondary)", padding: "8px 12px", borderRadius: 8, maxHeight: 80, overflowY: "auto" }}>
                        {s.reasoning}
                      </div>
                    </div>
                    <div style={{ padding: "8px 20px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)" }}>
                      <span>🕐 {new Date(s.created_at).toLocaleString("ar-SA")}</span>
                      {s.expires_at && <span>⏰ {new Date(s.expires_at).toLocaleString("ar-SA")}</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* PERFORMANCE TAB */}
      {activeTab === "performance" && (
        perfLoading ? <div style={{ textAlign: "center", padding: 60 }}><div className="spinner" /></div> :
        performance ? (
          <div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 14, marginBottom: 24 }}>
              {[
                { l: "إجمالي التوصيات", v: performance.total, i: "📋", c: undefined },
                { l: "ناجحة", v: performance.success, i: "✅", c: "#10b981" },
                { l: "وقف خسارة", v: performance.stopped, i: "❌", c: "#ef4444" },
                { l: "منتهية", v: performance.expired, i: "⏰", c: "#8e95ab" },
                { l: "نسبة النجاح", v: `${performance.success_rate ?? 0}%`, i: "🎯", c: (performance.success_rate ?? 0) >= 50 ? "#10b981" : "#ef4444" },
                { l: "متوسط الربح", v: `${(performance.avg_pnl_pct ?? 0) >= 0 ? "+" : ""}${performance.avg_pnl_pct ?? 0}%`, i: "📊", c: (performance.avg_pnl_pct ?? 0) >= 0 ? "#10b981" : "#ef4444" },
              ].map((s, i) => (
                <div key={i} className="card" style={{ padding: 16, textAlign: "center" }}>
                  <div style={{ fontSize: 24, marginBottom: 6 }}>{s.i}</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: s.c || "var(--text-primary)" }}>{s.v}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>{s.l}</div>
                </div>
              ))}
            </div>
            {performance.total === 0 && (
              <div className="card" style={{ textAlign: "center", padding: 40, color: "var(--text-muted)" }}>لا توجد توصيات مغلقة بعد لحساب الأداء</div>
            )}
            <div style={{ marginTop: 16, textAlign: "center" }}>
              <button className="btn" style={{ background: "rgba(239,68,68,0.08)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.2)", fontSize: 13, padding: "10px 24px" }}
                onClick={async () => {
                  if (!confirm("هل تريد حذف جميع التوصيات وإعادة تعيين الأداء؟")) return;
                  try {
                    const { data } = await paperApi.resetSignals();
                    setGenResult(data.message);
                    setPerformance(null);
                    fetchSignals();
                    loadPerformance();
                  } catch { setGenResult("❌ فشل إعادة التعيين"); }
                }}>
                🔄 إعادة تعيين الأداء
              </button>
            </div>
          </div>
        ) : <div className="card" style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>لا توجد بيانات</div>
      )}

      {/* BOT ANALYSIS TAB */}
      {activeTab === "bot" && (
        perfLoading ? <div style={{ textAlign: "center", padding: 60 }}><div className="spinner" /></div> :
        botAnalysis ? (
          <div style={{ maxWidth: 640 }}>
            <div className="card" style={{ padding: 24, marginBottom: 16 }}>
              <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>🧠 تحليل أداء البوت</h3>
              <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 18, lineHeight: 1.6 }}>{botAnalysis.analysis}</p>
              {botAnalysis.success_rate !== undefined && (
                <div style={{ display: "flex", gap: 12, marginBottom: 18 }}>
                  <div style={{ flex: 1, padding: 14, borderRadius: 10, background: "rgba(16,185,129,0.06)", textAlign: "center" }}>
                    <div style={{ fontSize: 22, fontWeight: 800, color: "#10b981" }}>{botAnalysis.success_rate}%</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>نسبة النجاح</div>
                  </div>
                  <div style={{ flex: 1, padding: 14, borderRadius: 10, background: "rgba(239,68,68,0.06)", textAlign: "center" }}>
                    <div style={{ fontSize: 22, fontWeight: 800, color: "#ef4444" }}>{botAnalysis.loss_rate}%</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>نسبة الخسارة</div>
                  </div>
                </div>
              )}
            </div>
            {botAnalysis.issues.length > 0 && (
              <div className="card" style={{ padding: 24, marginBottom: 16 }}>
                <h4 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12, color: "#ef4444" }}>🔍 المشاكل المكتشفة</h4>
                {botAnalysis.issues.map((issue, i) => (
                  <div key={i} style={{ padding: "10px 14px", marginBottom: 8, borderRadius: 8, background: "rgba(239,68,68,0.04)", border: "1px solid rgba(239,68,68,0.1)", fontSize: 13, lineHeight: 1.6 }}>{issue}</div>
                ))}
              </div>
            )}
            {botAnalysis.recommendations.length > 0 && (
              <div className="card" style={{ padding: 24 }}>
                <h4 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12, color: "#3b82f6" }}>💡 توصيات للتحسين</h4>
                {botAnalysis.recommendations.map((rec, i) => (
                  <div key={i} style={{ padding: "10px 14px", marginBottom: 8, borderRadius: 8, background: "rgba(59,130,246,0.04)", border: "1px solid rgba(59,130,246,0.1)", fontSize: 13, lineHeight: 1.6 }}>{rec}</div>
                ))}
              </div>
            )}
          </div>
        ) : <div className="card" style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>لا توجد بيانات كافية</div>
      )}
    </div>
  );
}

export default function SignalsPage() {
  return (
    <Suspense fallback={<div style={{ display: "flex", justifyContent: "center", padding: 60 }}><div className="spinner" /></div>}>
      <SignalsPageContent />
    </Suspense>
  );
}
