"use client";
import { useState, useEffect, useCallback } from "react";
import { paperApi, marketApi } from "@/lib/api";

interface Holding {
  id: string; symbol: string; asset: string; quantity: number; avg_buy_price: number;
}
interface WalletDetail {
  wallet: { id: string; label: string; initial_balance: number; current_balance: number; created_at: string };
  holdings: Holding[];
  total_pnl: number; total_pnl_pct: number; win_rate: number; total_trades: number;
}
interface PaperTrade {
  id: string; symbol: string; side: string; quantity: number; price: number;
  total_value: number; pnl: number; status: string; executed_by: string; created_at: string;
}
interface BotSettings {
  is_enabled: boolean; max_trades_per_day: number; max_trade_amount: number; max_portfolio_percentage: number;
}

export default function PaperTradingPage() {
  const [wallet, setWallet] = useState<WalletDetail | null>(null);
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [botSettings, setBotSettings] = useState<BotSettings | null>(null);
  const [symbols, setSymbols] = useState<any[]>([]);
  const [noWallet, setNoWallet] = useState(false);
  const [loading, setLoading] = useState(true);

  // Create wallet form
  const [createBalance, setCreateBalance] = useState(10000);

  // Manual trade form
  const [tradeSymbol, setTradeSymbol] = useState("BTCUSDT");
  const [tradeSide, setTradeSide] = useState("buy");
  const [tradeAmount, setTradeAmount] = useState(100);
  const [tradeLoading, setTradeLoading] = useState(false);
  const [tradeResult, setTradeResult] = useState<string>("");

  const [activeTab, setActiveTab] = useState<"wallet" | "trades" | "bot">("wallet");

  const fetchData = useCallback(async () => {
    try {
      const [wRes, tRes, bRes, sRes] = await Promise.allSettled([
        paperApi.getWallet(),
        paperApi.getTrades(50),
        paperApi.getBotSettings(),
        marketApi.getSymbols(),
      ]);
      if (wRes.status === "fulfilled") { setWallet(wRes.value.data); setNoWallet(false); }
      else setNoWallet(true);
      if (tRes.status === "fulfilled") setTrades(tRes.value.data);
      if (bRes.status === "fulfilled") setBotSettings(bRes.value.data);
      if (sRes.status === "fulfilled") setSymbols(sRes.value.data.filter((s: any) => s.is_active));
    } catch {} finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  async function handleCreateWallet() {
    try {
      await paperApi.createWallet({ initial_balance: createBalance });
      fetchData();
    } catch (e: any) { alert(e.response?.data?.detail || "خطأ"); }
  }

  async function handleResetWallet() {
    if (!confirm("هل تريد إعادة تعيين المحفظة الوهمية؟ سيتم حذف جميع الصفقات والأرصدة")) return;
    try {
      await paperApi.resetWallet({ initial_balance: createBalance });
      fetchData();
    } catch (e: any) { alert(e.response?.data?.detail || "خطأ"); }
  }

  async function handleTrade() {
    setTradeLoading(true); setTradeResult("");
    try {
      const { data } = await paperApi.executeTrade({ symbol: tradeSymbol, side: tradeSide, amount_usdt: tradeAmount });
      setTradeResult(`✅ ${tradeSide === "buy" ? "شراء" : "بيع"} ${data.quantity.toFixed(6)} ${tradeSymbol} @ $${data.price.toFixed(2)}`);
      fetchData();
    } catch (e: any) {
      setTradeResult(`❌ ${e.response?.data?.detail || "فشل التنفيذ"}`);
    } finally { setTradeLoading(false); }
  }

  async function toggleBot() {
    if (!botSettings) return;
    try {
      const { data } = await paperApi.updateBotSettings({ is_enabled: !botSettings.is_enabled });
      setBotSettings(data);
    } catch {}
  }

  if (loading) return <div style={{ padding: 40, textAlign: "center" }}><div className="spinner" /></div>;

  // No wallet — show create form
  if (noWallet) {
    return (
      <div style={{ padding: 32 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 8, color: "var(--text-primary)" }}>🧪 التداول الوهمي</h1>
        <p style={{ color: "var(--text-secondary)", marginBottom: 32, fontSize: 14 }}>أنشئ محفظة وهمية لاختبار استراتيجياتك بأسعار حقيقية وبدون مخاطرة</p>
        <div className="card" style={{ maxWidth: 480, padding: 32 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 20 }}>إنشاء محفظة وهمية</h3>
          <label style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 8 }}>الرصيد الابتدائي (USDT)</label>
          <input className="form-input" type="number" value={createBalance} onChange={e => setCreateBalance(+e.target.value)} min={100} step={100} />
          <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
            {[1000, 5000, 10000, 50000, 100000].map(v => (
              <button key={v} className={`btn ${createBalance === v ? "btn-primary" : "btn-secondary"}`} style={{ fontSize: 12, padding: "6px 12px" }}
                onClick={() => setCreateBalance(v)}>${v.toLocaleString()}</button>
            ))}
          </div>
          <button className="btn btn-primary" style={{ width: "100%", marginTop: 24, justifyContent: "center" }} onClick={handleCreateWallet}>
            🚀 إنشاء المحفظة الوهمية
          </button>
        </div>
      </div>
    );
  }

  const w = wallet!;

  return (
    <div style={{ padding: 32 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: "var(--text-primary)" }}>🧪 التداول الوهمي</h1>
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>تداول بأسعار حقيقية — بدون مخاطرة</p>
        </div>
        <button className="btn btn-secondary" style={{ fontSize: 12 }} onClick={handleResetWallet}>🔄 إعادة تعيين</button>
      </div>

      {/* Stats Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 16, marginBottom: 24 }}>
        {[
          { label: "الرصيد المتاح", value: `$${w.wallet.current_balance.toLocaleString(undefined, { maximumFractionDigits: 2 })}`, icon: "💵" },
          { label: "الربح/الخسارة", value: `${w.total_pnl >= 0 ? "+" : ""}$${w.total_pnl.toFixed(2)}`, icon: w.total_pnl >= 0 ? "📈" : "📉", color: w.total_pnl >= 0 ? "#10b981" : "#ef4444" },
          { label: "نسبة التغير", value: `${w.total_pnl_pct >= 0 ? "+" : ""}${w.total_pnl_pct.toFixed(1)}%`, icon: "📊", color: w.total_pnl_pct >= 0 ? "#10b981" : "#ef4444" },
          { label: "نسبة الفوز", value: `${w.win_rate.toFixed(0)}%`, icon: "🎯" },
          { label: "عدد الصفقات", value: w.total_trades.toString(), icon: "📋" },
        ].map((s, i) => (
          <div key={i} className="card" style={{ padding: 18, display: "flex", alignItems: "center", gap: 14 }}>
            <span style={{ fontSize: 28 }}>{s.icon}</span>
            <div>
              <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>{s.label}</div>
              <div style={{ fontSize: 18, fontWeight: 800, color: s.color || "var(--text-primary)" }}>{s.value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20, background: "var(--bg-secondary)", borderRadius: 10, padding: 4 }}>
        {(["wallet", "trades", "bot"] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            style={{
              flex: 1, padding: "10px 0", borderRadius: 8, border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600,
              background: activeTab === tab ? "var(--bg-primary)" : "transparent",
              color: activeTab === tab ? "var(--text-primary)" : "var(--text-muted)",
              boxShadow: activeTab === tab ? "0 1px 4px rgba(0,0,0,0.06)" : "none",
            }}>
            {tab === "wallet" ? "💼 المحفظة" : tab === "trades" ? "📋 الصفقات" : "🤖 البوت الوهمي"}
          </button>
        ))}
      </div>

      {/* Wallet Tab */}
      {activeTab === "wallet" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
          {/* Manual Trade */}
          <div className="card" style={{ padding: 24 }}>
            <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 18 }}>⚡ تداول يدوي</h3>
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>العملة</label>
              <select className="form-input" value={tradeSymbol} onChange={e => setTradeSymbol(e.target.value)}>
                {symbols.map(s => <option key={s.symbol} value={s.symbol}>{s.symbol}</option>)}
              </select>
            </div>
            <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
              <button className={`btn ${tradeSide === "buy" ? "btn-primary" : "btn-secondary"}`} style={{ flex: 1, justifyContent: "center" }}
                onClick={() => setTradeSide("buy")}>🟢 شراء</button>
              <button className={`btn ${tradeSide === "sell" ? "" : "btn-secondary"}`} style={{ flex: 1, justifyContent: "center", ...(tradeSide === "sell" ? { background: "linear-gradient(135deg, #ef4444, #dc2626)", color: "#fff" } : {}) }}
                onClick={() => setTradeSide("sell")}>🔴 بيع</button>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>المبلغ (USDT)</label>
              <input className="form-input" type="number" value={tradeAmount} onChange={e => setTradeAmount(+e.target.value)} min={5} />
            </div>
            <button className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }} onClick={handleTrade} disabled={tradeLoading}>
              {tradeLoading ? "جارٍ التنفيذ..." : "تنفيذ الصفقة"}
            </button>
            {tradeResult && <div style={{ marginTop: 12, fontSize: 13, padding: "10px 14px", borderRadius: 8, background: tradeResult.startsWith("✅") ? "rgba(16,185,129,0.08)" : "rgba(239,68,68,0.08)", color: tradeResult.startsWith("✅") ? "#10b981" : "#ef4444" }}>{tradeResult}</div>}
          </div>

          {/* Holdings */}
          <div className="card" style={{ padding: 24 }}>
            <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 18 }}>💼 المقتنيات</h3>
            {w.holdings.length === 0 ? (
              <div style={{ textAlign: "center", padding: 30, color: "var(--text-muted)", fontSize: 13 }}>لا توجد مقتنيات حالياً</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {w.holdings.map(h => (
                  <div key={h.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 14px", borderRadius: 10, background: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 700 }}>{h.asset}</div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{h.quantity.toFixed(6)}</div>
                    </div>
                    <div style={{ textAlign: "left" }}>
                      <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>متوسط الشراء</div>
                      <div style={{ fontSize: 14, fontWeight: 700 }}>${h.avg_buy_price.toFixed(2)}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Trades Tab */}
      {activeTab === "trades" && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "var(--bg-secondary)", borderBottom: "1px solid var(--border)" }}>
                {["العملة", "النوع", "الكمية", "السعر", "القيمة", "الربح/الخسارة", "المنفذ", "الوقت"].map(h => (
                  <th key={h} style={{ padding: "12px 14px", textAlign: "right", fontWeight: 600, color: "var(--text-secondary)", fontSize: 11 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.map(t => (
                <tr key={t.id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "10px 14px", fontWeight: 700 }}>{t.symbol}</td>
                  <td style={{ padding: "10px 14px" }}>
                    <span style={{ padding: "3px 10px", borderRadius: 6, fontSize: 11, fontWeight: 700, background: t.side === "buy" ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)", color: t.side === "buy" ? "#10b981" : "#ef4444" }}>
                      {t.side === "buy" ? "شراء" : "بيع"}
                    </span>
                  </td>
                  <td style={{ padding: "10px 14px" }}>{t.quantity.toFixed(6)}</td>
                  <td style={{ padding: "10px 14px" }}>${t.price.toFixed(2)}</td>
                  <td style={{ padding: "10px 14px" }}>${t.total_value.toFixed(2)}</td>
                  <td style={{ padding: "10px 14px", color: (t.pnl || 0) >= 0 ? "#10b981" : "#ef4444", fontWeight: 700 }}>
                    {t.side === "sell" ? `${t.pnl >= 0 ? "+" : ""}$${(t.pnl || 0).toFixed(2)}` : "—"}
                  </td>
                  <td style={{ padding: "10px 14px", fontSize: 11 }}>{t.executed_by === "paper_bot" ? "🤖 بوت" : "✋ يدوي"}</td>
                  <td style={{ padding: "10px 14px", fontSize: 11, color: "var(--text-muted)" }}>{new Date(t.created_at).toLocaleString("ar-SA")}</td>
                </tr>
              ))}
              {trades.length === 0 && (
                <tr><td colSpan={8} style={{ textAlign: "center", padding: 40, color: "var(--text-muted)" }}>لا توجد صفقات بعد</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Bot Settings Tab */}
      {activeTab === "bot" && botSettings && (
        <div className="card" style={{ maxWidth: 520, padding: 28 }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 20 }}>🤖 إعدادات البوت الوهمي</h3>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 20 }}>البوت الوهمي ينفذ صفقات تلقائياً بناءً على نتائج التحليل — بأسعار حقيقية ورصيد وهمي</p>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 18px", borderRadius: 10, background: botSettings.is_enabled ? "rgba(16,185,129,0.06)" : "var(--bg-secondary)", border: `1px solid ${botSettings.is_enabled ? "rgba(16,185,129,0.2)" : "var(--border)"}`, marginBottom: 20 }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700 }}>حالة البوت الوهمي</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{botSettings.is_enabled ? "مفعّل ويعمل" : "متوقف"}</div>
            </div>
            <button className={`btn ${botSettings.is_enabled ? "" : "btn-primary"}`}
              style={botSettings.is_enabled ? { background: "rgba(239,68,68,0.1)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.2)" } : {}}
              onClick={toggleBot}>
              {botSettings.is_enabled ? "إيقاف" : "تفعيل"}
            </button>
          </div>

          {[
            { label: "الحد الأقصى للصفقات يومياً", key: "max_trades_per_day", value: botSettings.max_trades_per_day },
            { label: "الحد الأقصى لكل صفقة (USDT)", key: "max_trade_amount", value: botSettings.max_trade_amount },
            { label: "نسبة المحفظة القصوى لكل صفقة (%)", key: "max_portfolio_percentage", value: botSettings.max_portfolio_percentage },
            { label: "الحد الأقصى للخسارة اليومية (USDT)", key: "max_daily_loss", value: (botSettings as any).max_daily_loss ?? 200 },
            { label: "الحد الأدنى لوقف الخسارة (USDT)", key: "min_loss_limit", value: (botSettings as any).min_loss_limit ?? 10 },
            { label: "الحد الأعلى لوقف الخسارة (USDT)", key: "max_loss_limit", value: (botSettings as any).max_loss_limit ?? 500 },
            { label: "الحد الأدنى لثقة التوصية (%)", key: "min_confidence", value: (botSettings as any).min_confidence ?? 40 },
            { label: "مضاعف مدة التوصية (1.0 = عادي, 2.0 = ضعف)", key: "signal_duration_multiplier", value: (botSettings as any).signal_duration_multiplier ?? 1.0 },
          ].map(field => (
            <div key={field.key} style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>{field.label}</label>
              <input className="form-input" type="number" step={field.key === "signal_duration_multiplier" ? "0.1" : "1"} defaultValue={field.value}
                onBlur={e => paperApi.updateBotSettings({ [field.key]: +e.target.value }).then(r => setBotSettings(r.data))} />
            </div>
          ))}

          {/* Wallet Balance Control */}
          <div style={{ padding: "16px 18px", borderRadius: 10, background: "rgba(59,130,246,0.04)", border: "1px solid rgba(59,130,246,0.1)", marginTop: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>💰 رصيد المحفظة الوهمية</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 10 }}>
              الرصيد الحالي: <strong style={{ color: "var(--text-primary)" }}>${w.wallet.current_balance.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              {[1000, 5000, 10000, 50000, 100000].map(v => (
                <button key={v} className="btn btn-secondary" style={{ fontSize: 11, padding: "5px 10px" }}
                  onClick={() => { setCreateBalance(v); paperApi.resetWallet({ initial_balance: v }).then(() => fetchData()); }}>
                  ${v.toLocaleString()}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
