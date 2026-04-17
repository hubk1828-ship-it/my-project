"use client";
import { useEffect, useState, useRef } from "react";
import { analysisApi, adminApi, WS_BASE } from "@/lib/api";
import type { Analysis, LiveCoin, TradeEvent } from "@/lib/types";

const coinColors: Record<string, string> = {
  BTC: "#f7931a", ETH: "#627eea", SOL: "#9945ff",
  BNB: "#f3ba2f", XRP: "#23292f", ADA: "#0033ad",
  DOGE: "#c3a634", AVAX: "#e84142",
};

function LiveCoinCard({ coin }: { coin: LiveCoin }) {
  const symbol = coin.base_asset;
  const color = coinColors[symbol] || "#3b82f6";
  const isUp = coin.change_24h >= 0;
  const decision = coin.analysis?.decision;
  const confidence = coin.analysis?.confidence || 0;

  return (
    <div className="card" style={{ padding: 20, position: "relative", overflow: "visible" }}>
      {/* Live indicator */}
      <div style={{ position: "absolute", top: 12, left: 12 }}>
        <span className="pulse-dot" />
      </div>

      {/* Header: coin info + price */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 44, height: 44, borderRadius: "50%",
            background: `${color}15`, color,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 18, fontWeight: 800,
            border: `2px solid ${color}30`,
          }}>{symbol[0]}</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>{symbol}</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{coin.symbol}</div>
          </div>
        </div>
        <div style={{ textAlign: "left" }}>
          <div style={{ fontWeight: 800, fontSize: 18, letterSpacing: "-0.02em" }}>
            ${coin.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: coin.price < 1 ? 6 : 2 })}
          </div>
          <div style={{
            fontSize: 13, fontWeight: 600,
            color: isUp ? "#059669" : "#dc2626",
            display: "flex", alignItems: "center", gap: 4, justifyContent: "flex-end",
          }}>
            {isUp ? "▲" : "▼"} {Math.abs(coin.change_24h).toFixed(2)}%
          </div>
        </div>
      </div>

      {/* 24h Stats */}
      <div style={{
        display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8,
        padding: "12px 0", borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)",
        marginBottom: 14,
      }}>
        <div>
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>أعلى 24h</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#059669" }}>${coin.high_24h.toLocaleString()}</div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>أدنى 24h</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#dc2626" }}>${coin.low_24h.toLocaleString()}</div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>الحجم</div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            {coin.volume_24h > 1e9 ? `${(coin.volume_24h / 1e9).toFixed(1)}B` :
             coin.volume_24h > 1e6 ? `${(coin.volume_24h / 1e6).toFixed(1)}M` :
             coin.volume_24h.toLocaleString()}
          </div>
        </div>
      </div>

      {/* Analysis Result */}
      {coin.analysis ? (
        <>
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10,
          }}>
            <span className={`badge ${decision === "buy" ? "badge-green" : decision === "sell" ? "badge-red" : "badge-amber"}`}>
              {decision === "buy" ? "📈 شراء" : decision === "sell" ? "📉 بيع" : "⏸ انتظار"}
            </span>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {coin.analysis.created_at ? new Date(coin.analysis.created_at).toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" }) : ""}
            </span>
          </div>

          {/* Technical indicators */}
          {coin.analysis.technical_indicators && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 10 }}>
              <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                RSI: <strong>{coin.analysis.technical_indicators.rsi?.toFixed(1)}</strong>
              </div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                الاتجاه: <strong>{coin.analysis.technical_indicators.trend}</strong>
              </div>
            </div>
          )}

          {/* Confidence bar */}
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
              <span>مستوى الثقة</span><span style={{ fontWeight: 700 }}>{confidence}%</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{
                width: `${confidence}%`,
                background: confidence >= 70 ? "var(--accent-green)" : confidence >= 40 ? "var(--accent-amber)" : "var(--accent-red)",
              }} />
            </div>
          </div>
        </>
      ) : (
        <div style={{ textAlign: "center", padding: "12px 0", color: "var(--text-muted)", fontSize: 13 }}>
          لم يتم التحليل بعد
        </div>
      )}
    </div>
  );
}

function TradeEventToast({ event }: { event: TradeEvent }) {
  return (
    <div className="slide-in" style={{
      padding: "14px 18px",
      background: event.success ? "rgba(16,185,129,0.08)" : "rgba(239,68,68,0.08)",
      border: `1px solid ${event.success ? "rgba(16,185,129,0.2)" : "rgba(239,68,68,0.2)"}`,
      borderRadius: 12,
      display: "flex", alignItems: "center", gap: 12,
      marginBottom: 8,
    }}>
      <span style={{ fontSize: 22 }}>{event.success ? "✅" : "❌"}</span>
      <div>
        <div style={{ fontWeight: 600, fontSize: 14 }}>
          {event.success ? "تم تنفيذ صفقة" : "فشل تنفيذ صفقة"} — {event.symbol}
        </div>
        {event.success && (
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
            {event.side === "buy" ? "شراء" : "بيع"} · {event.quantity} · ${event.price.toLocaleString()} · القيمة: ${event.total_value.toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [liveCoins, setLiveCoins] = useState<LiveCoin[]>([]);
  const [tradeEvents, setTradeEvents] = useState<TradeEvent[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningAnalysis, setRunningAnalysis] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const [role, setRole] = useState("user");

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) {
      try {
        const payload = JSON.parse(atob(token.split(".")[1]));
        setRole(payload.role || "user");
      } catch {}
    }

    loadAnalyses();
    connectWebSocket();

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  function connectWebSocket() {
    try {
      const ws = new WebSocket(`${WS_BASE}/ws/live-analysis`);
      wsRef.current = ws;

      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => {
        setWsConnected(false);
        setTimeout(connectWebSocket, 5000);
      };
      ws.onerror = () => setWsConnected(false);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "live_update" && data.coins) {
            setLiveCoins(data.coins);
          } else if (data.type === "trade_event") {
            setTradeEvents(prev => [data, ...prev].slice(0, 10));
          }
        } catch {}
      };
    } catch {
      setTimeout(connectWebSocket, 5000);
    }
  }

  async function loadAnalyses() {
    try {
      const { data } = await analysisApi.getToday();
      setAnalyses(data);
    } catch {}
    setLoading(false);
  }

  async function triggerAnalysis() {
    setRunningAnalysis(true);
    try {
      await adminApi.runAnalysis();
      setTimeout(loadAnalyses, 3000);
    } catch {}
    setRunningAnalysis(false);
  }

  const opportunities = analyses.filter((a) => a.decision !== "no_opportunity");

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4, letterSpacing: "-0.02em" }}>
            📡 التقارير المباشرة
          </h1>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--text-secondary)" }}>
            <span className="pulse-dot" style={{ background: wsConnected ? "var(--accent-green)" : "var(--accent-red)" }} />
            {wsConnected ? "متصل — تحديث لحظي" : "غير متصل — جاري إعادة الاتصال..."}
          </div>
        </div>
        {role === "admin" && (
          <button className="btn btn-primary" onClick={triggerAnalysis} disabled={runningAnalysis}>
            {runningAnalysis ? "⏳ جاري التحليل..." : "🔄 تشغيل التحليل"}
          </button>
        )}
      </div>

      {/* Stats */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        <div className="stat-card count-up" style={{ borderRight: "3px solid var(--accent-green)" }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8, fontWeight: 600 }}>✅ فرص مرصودة</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: "#059669" }}>{opportunities.length}</div>
        </div>
        <div className="stat-card count-up" style={{ borderRight: "3px solid var(--accent-blue)" }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8, fontWeight: 600 }}>🔍 عملات نشطة</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: "var(--accent-blue)" }}>{liveCoins.length || analyses.length}</div>
        </div>
        <div className="stat-card count-up" style={{ borderRight: "3px solid var(--accent-amber)" }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8, fontWeight: 600 }}>⚠️ لا فرصة</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: "#d97706" }}>{analyses.filter(a => a.decision === "no_opportunity").length}</div>
        </div>
        <div className="stat-card count-up" style={{ borderRight: "3px solid var(--accent-purple)" }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8, fontWeight: 600 }}>⚡ صفقات آلية</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: "#7c3aed" }}>{tradeEvents.filter(e => e.success).length}</div>
        </div>
      </div>

      {/* Trade Events Feed */}
      {tradeEvents.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h3 className="section-title">⚡ آخر الصفقات المنفذة</h3>
          {tradeEvents.slice(0, 3).map((event, i) => (
            <TradeEventToast key={i} event={event} />
          ))}
        </div>
      )}

      {/* Live Coins Grid */}
      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 60 }}>
          <div className="spinner" />
        </div>
      ) : liveCoins.length > 0 ? (
        <>
          <h3 className="section-title">📊 أسعار وتحليلات حية</h3>
          <div className="grid-3" style={{ marginBottom: 24 }}>
            {liveCoins.map((coin) => (
              <LiveCoinCard key={coin.symbol} coin={coin} />
            ))}
          </div>
        </>
      ) : analyses.length > 0 ? (
        <>
          <h3 className="section-title">📊 تحليلات اليوم</h3>
          <div className="grid-3" style={{ marginBottom: 24 }}>
            {analyses.map((a) => {
              const symbol = a.symbol.replace("USDT", "");
              const color = coinColors[symbol] || "#3b82f6";
              const confidence = a.confidence_score || 0;
              return (
                <div key={a.id} className={`card analysis-card ${a.decision}`} style={{ padding: 20 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div style={{
                        width: 40, height: 40, borderRadius: "50%",
                        background: `${color}15`, color,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 16, fontWeight: 800,
                      }}>{symbol[0]}</div>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 15 }}>{symbol}</div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{a.symbol}</div>
                      </div>
                    </div>
                    <span className={`badge ${a.decision === "buy" ? "badge-green" : a.decision === "sell" ? "badge-red" : "badge-amber"}`}>
                      {a.decision === "buy" ? "📈 شراء" : a.decision === "sell" ? "📉 بيع" : "⏸ انتظار"}
                    </span>
                  </div>
                  <div style={{ marginBottom: 10 }}>
                    {a.reasoning.split("\n").map((line, i) => (
                      <div key={i} style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 3 }}>{line}</div>
                    ))}
                  </div>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
                      <span>الثقة</span><span>{confidence}%</span>
                    </div>
                    <div className="bar-track">
                      <div className="bar-fill" style={{
                        width: `${confidence}%`,
                        background: confidence >= 70 ? "var(--accent-green)" : confidence >= 40 ? "var(--accent-amber)" : "var(--accent-red)",
                      }} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <div className="card empty-state">
          <div className="empty-state-icon">📊</div>
          <div className="empty-state-title">لم يتم إجراء تحليلات اليوم بعد</div>
          <div className="empty-state-text">التحليل التلقائي يعمل كل ساعة — أو شغّل التحليل يدوياً</div>
        </div>
      )}
    </div>
  );
}
