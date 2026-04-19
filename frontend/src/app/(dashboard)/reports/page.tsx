"use client";
import { useEffect, useState, useRef } from "react";
import { analysisApi, marketApi, adminApi, WS_BASE } from "@/lib/api";
import type { Analysis, LiveCoin, SMCData, SMCOrderBlock, SMCFairValueGap, SupportedSymbol } from "@/lib/types";

const TIMEFRAMES = [
  { value: "1m", label: "1 دقيقة" },
  { value: "5m", label: "5 دقائق" },
  { value: "15m", label: "15 دقيقة" },
  { value: "30m", label: "30 دقيقة" },
  { value: "1h", label: "1 ساعة" },
  { value: "4h", label: "4 ساعات" },
  { value: "1d", label: "يومي" },
  { value: "1w", label: "أسبوعي" },
];
const coinColors: Record<string, string> = {
  BTC: "#f7931a", ETH: "#627eea", SOL: "#9945ff", BNB: "#f3ba2f",
  XRP: "#23292f", ADA: "#0033ad", DOGE: "#c3a634", AVAX: "#e84142",
};

interface LiveAnalysisResult {
  symbol: string; timeframe: string; trend: string;
  rsi: number; ema20: number; ema50: number;
  support: number; resistance: number; current_price: number;
  volume_ratio: number; smc: SMCData | null;
  smc_signal: { decision: string; confidence: number; signals: string[] } | null;
}

export default function ReportsPage() {
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [liveCoins, setLiveCoins] = useState<LiveCoin[]>([]);
  const [symbols, setSymbols] = useState<SupportedSymbol[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [selectedTF, setSelectedTF] = useState("1h");
  const [liveResult, setLiveResult] = useState<LiveAnalysisResult | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    loadData();
    connectWS();
    return () => { if (wsRef.current) wsRef.current.close(); };
  }, []);

  function connectWS() {
    try {
      const ws = new WebSocket(`${WS_BASE}/ws/live-analysis`);
      wsRef.current = ws;
      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => { setWsConnected(false); setTimeout(connectWS, 5000); };
      ws.onerror = () => setWsConnected(false);
      ws.onmessage = (e) => { try { const d = JSON.parse(e.data); if (d.type === "live_update" && d.coins) setLiveCoins(d.coins); } catch {} };
    } catch { setTimeout(connectWS, 5000); }
  }

  async function loadData() {
    try {
      const [aRes, sRes] = await Promise.all([
        analysisApi.getHistory(undefined, 50),
        marketApi.getSymbols(),
      ]);
      setAnalyses(aRes.data);
      setSymbols(sRes.data.filter((s: SupportedSymbol) => s.is_active));
    } catch {}
    setLoading(false);
  }

  async function runLiveAnalysis(sym: string, tf: string) {
    setAnalyzing(true);
    setLiveResult(null);
    try {
      const { data } = await analysisApi.liveAnalysis(sym, tf);
      setLiveResult(data);
    } catch (err: any) {
      console.error(err);
    }
    setAnalyzing(false);
  }

  async function runFullAnalysis() {
    setRefreshing(true);
    setAnalyses([]); // Clear UI immediately

    try {
      // Step 1: Clear all old analyses and wait
      await analysisApi.clearAll();

      // Step 2: Trigger new analysis
      await adminApi.runAnalysis();

      // Step 3: Wait 5 seconds for first results, then poll every 3s
      await new Promise(r => setTimeout(r, 5000));
      for (let i = 0; i < 20; i++) {
        const { data } = await analysisApi.getHistory(undefined, 50);
        if (data.length > 0) {
          setAnalyses(data);
          // Keep polling a few more times for remaining symbols
          for (let j = 0; j < 5; j++) {
            await new Promise(r => setTimeout(r, 3000));
            const { data: updated } = await analysisApi.getHistory(undefined, 50);
            setAnalyses(updated);
          }
          break;
        }
        await new Promise(r => setTimeout(r, 3000));
      }
    } catch {}

    // Final sync
    try {
      const { data } = await analysisApi.getHistory(undefined, 50);
      setAnalyses(data);
    } catch {}
    setRefreshing(false);
  }

  const filtered = selectedSymbol ? analyses.filter(a => a.symbol === selectedSymbol) : analyses;
  const buyCount = analyses.filter(a => a.decision === "buy").length;
  const sellCount = analyses.filter(a => a.decision === "sell").length;

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><div className="spinner" /></div>;

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800 }}>📊 التحليل اليومي — Smart Money Concepts</h1>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--text-secondary)", marginTop: 4 }}>
            <span className="pulse-dot" style={{ background: wsConnected ? "var(--accent-green)" : "var(--accent-red)" }} />
            {wsConnected ? "متصل — تحديث لحظي" : "غير متصل"}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-primary" onClick={runFullAnalysis} disabled={refreshing}
            style={{ padding: "10px 22px", fontSize: 14, fontWeight: 700 }}>
            {refreshing ? "⏳ جاري التحديث..." : "🔄 تحديث الآن"}
          </button>
        </div>
      </div>

      {/* === Timeframe Analyzer Section === */}
      <div className="card" style={{ padding: 24, marginBottom: 24, border: "2px solid var(--accent-blue)", borderRadius: 14 }}>
        <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 20 }}>🔬</span> تحليل لحظي بفريم مخصص
        </div>

        <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap", marginBottom: 16 }}>
          {/* Symbol selector */}
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>العملة</label>
            <select className="form-input" value={selectedSymbol || ""} onChange={e => setSelectedSymbol(e.target.value || null)}
              style={{ width: 160, padding: "10px 14px", fontSize: 14, fontWeight: 600 }}>
              <option value="">اختر عملة</option>
              {symbols.map(s => <option key={s.symbol} value={s.symbol}>{s.base_asset} / {s.quote_asset}</option>)}
            </select>
          </div>

          {/* Timeframe selector */}
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>الإطار الزمني</label>
            <div style={{ display: "flex", gap: 4 }}>
              {TIMEFRAMES.map(tf => (
                <button key={tf.value}
                  className={`btn ${selectedTF === tf.value ? "btn-primary" : "btn-ghost"}`}
                  style={{ fontSize: 12, padding: "8px 12px", fontWeight: selectedTF === tf.value ? 700 : 400 }}
                  onClick={() => setSelectedTF(tf.value)}>
                  {tf.value}
                </button>
              ))}
            </div>
          </div>

          {/* Analyze button */}
          <button className="btn btn-primary" disabled={!selectedSymbol || analyzing}
            style={{ padding: "10px 24px", fontSize: 14, fontWeight: 700 }}
            onClick={() => selectedSymbol && runLiveAnalysis(selectedSymbol, selectedTF)}>
            {analyzing ? <span className="spinner" style={{ width: 16, height: 16 }} /> : "🔍 حلّل الآن"}
          </button>
        </div>

        {/* Live Result */}
        {liveResult && (
          <div className="slide-in" style={{ marginTop: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{
                  width: 44, height: 44, borderRadius: "50%",
                  background: `${coinColors[liveResult.symbol.replace("USDT", "")] || "#3b82f6"}15`,
                  color: coinColors[liveResult.symbol.replace("USDT", "")] || "#3b82f6",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 18, fontWeight: 800,
                }}>{liveResult.symbol.replace("USDT", "")[0]}</div>
                <div>
                  <div style={{ fontWeight: 800, fontSize: 18 }}>{liveResult.symbol.replace("USDT", "")}</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>فريم: {TIMEFRAMES.find(t => t.value === liveResult.timeframe)?.label}</div>
                </div>
              </div>
              <div style={{ textAlign: "left" }}>
                <div style={{ fontSize: 22, fontWeight: 800 }}>${liveResult.current_price?.toLocaleString()}</div>
                {liveResult.smc_signal && (
                  <span className={`badge ${liveResult.smc_signal.decision === "buy" ? "badge-green" : liveResult.smc_signal.decision === "sell" ? "badge-red" : "badge-amber"}`} style={{ fontSize: 13 }}>
                    {liveResult.smc_signal.decision === "buy" ? "📈 شراء" : liveResult.smc_signal.decision === "sell" ? "📉 بيع" : "⏸ انتظار"}
                    {" "}{liveResult.smc_signal.confidence}%
                  </span>
                )}
              </div>
            </div>

            {/* Technical Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 0, border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", marginBottom: 16 }}>
              {[
                { label: "RSI", value: liveResult.rsi?.toFixed(1), color: (liveResult.rsi || 0) > 70 ? "#dc2626" : (liveResult.rsi || 0) < 30 ? "#059669" : undefined },
                { label: "الاتجاه", value: liveResult.trend },
                { label: "حجم", value: liveResult.volume_ratio ? `${liveResult.volume_ratio}x` : "—" },
                { label: "EMA20", value: liveResult.ema20 ? `$${liveResult.ema20.toLocaleString()}` : "—" },
                { label: "الدعم", value: liveResult.support ? `$${liveResult.support.toLocaleString()}` : "—", color: "#059669" },
                { label: "المقاومة", value: liveResult.resistance ? `$${liveResult.resistance.toLocaleString()}` : "—", color: "#dc2626" },
              ].map((item, i) => (
                <div key={i} style={{ padding: "12px 14px", borderRight: i < 5 ? "1px solid var(--border)" : "none", background: "var(--bg-primary)" }}>
                  <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 3 }}>{item.label}</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: item.color || "var(--text-primary)" }}>{item.value || "—"}</div>
                </div>
              ))}
            </div>

            {/* SMC Data */}
            {liveResult.smc && (
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}>
                  <span>🧠</span> SMC — {TIMEFRAMES.find(t => t.value === liveResult.timeframe)?.label}
                </div>
                <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
                  <span className={`badge ${liveResult.smc.trend === "bullish" ? "badge-green" : liveResult.smc.trend === "bearish" ? "badge-red" : "badge-amber"}`}>
                    Swing: {liveResult.smc.trend === "bullish" ? "صاعد ↑" : liveResult.smc.trend === "bearish" ? "هابط ↓" : "محايد"}
                  </span>
                  <span className={`badge ${liveResult.smc.internal_trend === "bullish" ? "badge-green" : liveResult.smc.internal_trend === "bearish" ? "badge-red" : "badge-amber"}`}>
                    Internal: {liveResult.smc.internal_trend === "bullish" ? "صاعد ↑" : liveResult.smc.internal_trend === "bearish" ? "هابط ↓" : "محايد"}
                  </span>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  {/* Structure Breaks */}
                  {liveResult.smc.structure_breaks.length > 0 && (
                    <div style={{ padding: 14, background: "var(--bg-primary)", borderRadius: 10 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>كسور هيكلية ({liveResult.smc.structure_breaks.length})</div>
                      {liveResult.smc.structure_breaks.map((brk, i) => (
                        <span key={i} className={`badge ${brk.bias === "bullish" ? "badge-green" : "badge-red"}`} style={{ fontSize: 11, marginLeft: 4, marginBottom: 4 }}>
                          {brk.type} {brk.bias === "bullish" ? "↑" : "↓"} ${brk.level.toLocaleString()}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Order Blocks */}
                  {liveResult.smc.order_blocks.length > 0 && (
                    <div style={{ padding: 14, background: "var(--bg-primary)", borderRadius: 10 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>بلوكات OB ({liveResult.smc.order_blocks.length})</div>
                      {liveResult.smc.order_blocks.map((ob: SMCOrderBlock, i: number) => (
                        <div key={i} style={{
                          fontSize: 12, padding: "4px 8px", marginBottom: 4, borderRadius: 6,
                          borderRight: `3px solid ${ob.bias === "bullish" ? "#10b981" : "#ef4444"}`,
                          background: ob.bias === "bullish" ? "rgba(16,185,129,0.05)" : "rgba(239,68,68,0.05)",
                        }}>
                          {ob.bias === "bullish" ? "🟢" : "🔴"} ${ob.low.toLocaleString()} — ${ob.high.toLocaleString()}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* FVG */}
                  {liveResult.smc.fair_value_gaps.length > 0 && (
                    <div style={{ padding: 14, background: "var(--bg-primary)", borderRadius: 10 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>فجوات FVG ({liveResult.smc.fair_value_gaps.length})</div>
                      {liveResult.smc.fair_value_gaps.map((fvg: SMCFairValueGap, i: number) => (
                        <div key={i} style={{
                          fontSize: 12, padding: "4px 8px", marginBottom: 4, borderRadius: 6,
                          borderRight: `3px solid ${fvg.bias === "bullish" ? "#10b981" : "#ef4444"}`,
                          background: fvg.bias === "bullish" ? "rgba(16,185,129,0.05)" : "rgba(239,68,68,0.05)",
                        }}>
                          {fvg.bias === "bullish" ? "📗" : "📕"} ${fvg.bottom.toLocaleString()} — ${fvg.top.toLocaleString()}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Equal Levels */}
                  {liveResult.smc.equal_levels.length > 0 && (
                    <div style={{ padding: 14, background: "var(--bg-primary)", borderRadius: 10 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>مستويات سيولة ({liveResult.smc.equal_levels.length})</div>
                      {liveResult.smc.equal_levels.map((eq, i) => (
                        <span key={i} className={`badge ${eq.type === "EQH" ? "badge-red" : "badge-green"}`} style={{ fontSize: 11, marginLeft: 4, marginBottom: 4 }}>
                          {eq.type} ${eq.price.toLocaleString()}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Zones */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr", gap: 8, marginTop: 12 }}>
                  {[
                    { label: "قمة قوية", val: liveResult.smc.strong_high, color: "#dc2626" },
                    { label: "قمة ضعيفة", val: liveResult.smc.weak_high, color: "#d97706" },
                    { label: "التوازن", val: liveResult.smc.equilibrium, color: "var(--text-primary)" },
                    { label: "قاع ضعيف", val: liveResult.smc.weak_low, color: "#d97706" },
                    { label: "قاع قوي", val: liveResult.smc.strong_low, color: "#059669" },
                  ].filter(z => z.val).map((z, i) => (
                    <div key={i} style={{ padding: 10, background: "var(--bg-primary)", borderRadius: 8, textAlign: "center" }}>
                      <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{z.label}</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: z.color }}>${z.val!.toLocaleString()}</div>
                    </div>
                  ))}
                </div>

                {/* SMC Signals */}
                {liveResult.smc_signal && (
                  <div style={{ marginTop: 14, padding: 14, background: "var(--bg-primary)", borderRadius: 10 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>📋 إشارات SMC</div>
                    {liveResult.smc_signal.signals.map((sig, i) => (
                      <div key={i} style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.8 }}>{sig}</div>
                    ))}
                    <div style={{ marginTop: 10 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>
                        <span>الثقة SMC</span><span style={{ fontWeight: 700 }}>{liveResult.smc_signal.confidence}%</span>
                      </div>
                      <div className="bar-track">
                        <div className="bar-fill" style={{
                          width: `${liveResult.smc_signal.confidence}%`,
                          background: liveResult.smc_signal.confidence >= 65 ? "var(--accent-green)" : liveResult.smc_signal.confidence >= 35 ? "var(--accent-amber)" : "var(--accent-red)",
                        }} />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Live Ticker */}
      {liveCoins.length > 0 && (
        <div style={{ display: "flex", gap: 12, overflowX: "auto", paddingBottom: 8, marginBottom: 20, scrollbarWidth: "none" }}>
          {liveCoins.map(coin => {
            const isUp = coin.change_24h >= 0;
            return (
              <div key={coin.symbol} className="card" style={{
                padding: "14px 20px", minWidth: 180, cursor: "pointer", flexShrink: 0, position: "relative",
                borderBottom: selectedSymbol === coin.symbol ? "3px solid var(--accent-blue)" : "none",
              }} onClick={() => { setSelectedSymbol(coin.symbol); runLiveAnalysis(coin.symbol, selectedTF); }}>
                <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{coin.base_asset}</div>
                <div style={{ fontWeight: 800, fontSize: 16 }}>
                  ${coin.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: coin.price < 1 ? 6 : 2 })}
                </div>
                <div style={{ fontSize: 12, fontWeight: 600, color: isUp ? "#059669" : "#dc2626" }}>
                  {isUp ? "▲" : "▼"} {Math.abs(coin.change_24h).toFixed(2)}%
                </div>
                <span className="pulse-dot" style={{ position: "absolute", top: 8, left: 8, width: 6, height: 6 }} />
              </div>
            );
          })}
        </div>
      )}

      {/* Stats */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        <div className="stat-card" style={{ borderRight: "3px solid var(--accent-blue)" }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6, fontWeight: 600 }}>📊 تحليلات</div>
          <div style={{ fontSize: 28, fontWeight: 800 }}>{analyses.length}</div>
        </div>
        <div className="stat-card" style={{ borderRight: "3px solid var(--accent-green)" }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6, fontWeight: 600 }}>📈 شراء</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: "#059669" }}>{buyCount}</div>
        </div>
        <div className="stat-card" style={{ borderRight: "3px solid var(--accent-red)" }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6, fontWeight: 600 }}>📉 بيع</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: "#dc2626" }}>{sellCount}</div>
        </div>
        <div className="stat-card" style={{ borderRight: "3px solid var(--accent-amber)" }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6, fontWeight: 600 }}>⏸ انتظار</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: "#d97706" }}>{analyses.length - buyCount - sellCount}</div>
        </div>
      </div>

      {/* Filter by symbol */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        <button className={`btn ${!selectedSymbol ? "btn-primary" : "btn-ghost"}`}
          onClick={() => setSelectedSymbol(null)} style={{ fontSize: 12, padding: "7px 16px" }}>الكل</button>
        {[...new Set(analyses.map(a => a.symbol))].map(s => (
          <button key={s} className={`btn ${selectedSymbol === s ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setSelectedSymbol(s)} style={{ fontSize: 12, padding: "7px 16px" }}>
            {s.replace("USDT", "")}
          </button>
        ))}
      </div>

      {/* Saved Analysis Cards */}
      <div className="grid-2">
        {filtered.map(a => {
          const symbol = a.symbol.replace("USDT", "");
          const color = coinColors[symbol] || "#3b82f6";
          const confidence = a.confidence_score || 0;
          const indicators = a.technical_indicators || {};
          const smcData: SMCData | null = indicators.smc || null;

          return (
            <div key={a.id} className={`card analysis-card ${a.decision} animate-in`} style={{ padding: 0 }}>
              <div style={{ padding: "20px 24px", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{
                    width: 44, height: 44, borderRadius: "50%",
                    background: `${color}15`, color,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 18, fontWeight: 800, border: `2px solid ${color}30`,
                  }}>{symbol[0]}</div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 17 }}>{symbol}</div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      {(() => {
                        // Ensure it's parsed as UTC string so local time is correctly derived
                        const dtStr = a.created_at.endsWith("Z") ? a.created_at : `${a.created_at}Z`;
                        return new Date(dtStr).toLocaleString("ar-SA", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" });
                      })()}
                    </div>
                  </div>
                </div>
                <span className={`badge ${a.decision === "buy" ? "badge-green" : a.decision === "sell" ? "badge-red" : "badge-amber"}`}>
                  {a.decision === "buy" ? "📈 شراء" : a.decision === "sell" ? "📉 بيع" : "⏸ انتظار"}
                </span>
              </div>

              {/* Tech grid */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 0, borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>
                {[
                  { label: "RSI", value: indicators.rsi?.toFixed(1), color: (indicators.rsi || 0) > 70 ? "#dc2626" : (indicators.rsi || 0) < 30 ? "#059669" : undefined },
                  { label: "الاتجاه", value: indicators.trend },
                  { label: "حجم", value: indicators.volume_ratio ? `${indicators.volume_ratio}x` : "—" },
                ].map((item, i) => (
                  <div key={i} style={{ padding: "10px 14px", borderRight: i < 2 ? "1px solid var(--border)" : "none" }}>
                    <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>{item.label}</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: item.color || "var(--text-primary)" }}>{item.value || "—"}</div>
                  </div>
                ))}
              </div>

              {/* SMC badges */}
              {smcData && (
                <div style={{ padding: "12px 24px", borderBottom: "1px solid var(--border)", display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <span className={`badge ${smcData.trend === "bullish" ? "badge-green" : smcData.trend === "bearish" ? "badge-red" : "badge-amber"}`} style={{ fontSize: 11 }}>
                    SMC: {smcData.trend === "bullish" ? "صاعد" : smcData.trend === "bearish" ? "هابط" : "محايد"}
                  </span>
                  {smcData.structure_breaks.slice(-2).map((brk, i) => (
                    <span key={i} className={`badge ${brk.bias === "bullish" ? "badge-green" : "badge-red"}`} style={{ fontSize: 11 }}>
                      {brk.type} {brk.bias === "bullish" ? "↑" : "↓"}
                    </span>
                  ))}
                  {smcData.order_blocks.length > 0 && <span className="badge badge-blue" style={{ fontSize: 11 }}>{smcData.order_blocks.length} OB</span>}
                  {smcData.fair_value_gaps.length > 0 && <span className="badge badge-purple" style={{ fontSize: 11 }}>{smcData.fair_value_gaps.length} FVG</span>}
                </div>
              )}

              {/* Reasoning + Confidence */}
              <div style={{ padding: "16px 24px" }}>
                {a.reasoning.split("\n").slice(0, 5).map((line, i) => (
                  <div key={i} style={{ fontSize: 13, color: line.includes("━━━") ? "var(--accent-blue)" : "var(--text-secondary)", marginBottom: 2, lineHeight: 1.7, fontWeight: line.includes("━━━") ? 700 : 400 }}>{line}</div>
                ))}
                <div style={{ marginTop: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>
                    <span>TA + SMC</span><span style={{ fontWeight: 700 }}>{confidence}%</span>
                  </div>
                  <div className="bar-track">
                    <div className="bar-fill" style={{
                      width: `${confidence}%`,
                      background: confidence >= 65 ? "var(--accent-green)" : confidence >= 35 ? "var(--accent-amber)" : "var(--accent-red)",
                    }} />
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {filtered.length === 0 && (
        <div className="card empty-state">
          <div className="empty-state-icon">📊</div>
          <div className="empty-state-title">لا توجد تحليلات</div>
          <div className="empty-state-text">اختر عملة وفريم واضغط &quot;حلّل الآن&quot;</div>
        </div>
      )}
    </div>
  );
}
