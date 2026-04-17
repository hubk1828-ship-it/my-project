"use client";
import { useEffect, useState, useRef } from "react";
import { marketApi, WS_BASE } from "@/lib/api";
import type { SupportedSymbol, SuggestedCoin, LiveCoin } from "@/lib/types";

export default function AdminSymbolsPage() {
  const [symbols, setSymbols] = useState<SupportedSymbol[]>([]);
  const [suggested, setSuggested] = useState<SuggestedCoin[]>([]);
  const [liveCoins, setLiveCoins] = useState<LiveCoin[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ symbol: "", base_asset: "", quote_asset: "USDT" });
  const [msg, setMsg] = useState("");
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
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === "live_update" && data.coins) setLiveCoins(data.coins);
        } catch {}
      };
    } catch { setTimeout(connectWS, 5000); }
  }

  async function loadData() {
    try {
      const [sRes, sgRes] = await Promise.all([
        marketApi.getSymbols(),
        marketApi.getSuggestedCoins(),
      ]);
      setSymbols(sRes.data);
      setSuggested(sgRes.data);
    } catch {}
    setLoading(false);
  }

  async function addSymbol(e: React.FormEvent) {
    e.preventDefault();
    try {
      await marketApi.addSymbol(form);
      setMsg("✅ تم إضافة العملة");
      setShowAdd(false);
      setForm({ symbol: "", base_asset: "", quote_asset: "USDT" });
      loadData();
    } catch (err: any) {
      setMsg(`❌ ${err.response?.data?.detail || "فشل الإضافة"}`);
    }
    setTimeout(() => setMsg(""), 3000);
  }

  async function addSuggested(coin: SuggestedCoin) {
    try {
      const base = coin.symbol.replace("USDT", "");
      await marketApi.addSymbol({ symbol: coin.symbol, base_asset: base });
      setMsg(`✅ تم إضافة ${coin.name}`);
      loadData();
    } catch (err: any) {
      setMsg(`❌ ${err.response?.data?.detail || "فشل"}`);
    }
    setTimeout(() => setMsg(""), 3000);
  }

  async function toggleSymbol(id: string, currentActive: boolean) {
    try {
      await marketApi.updateSymbol(id, { is_active: !currentActive });
      loadData();
    } catch {}
  }

  async function deleteSymbol(id: string) {
    if (!confirm("هل أنت متأكد من حذف هذه العملة؟")) return;
    try {
      await marketApi.deleteSymbol(id);
      loadData();
    } catch {}
  }

  function getLivePrice(symbol: string): LiveCoin | undefined {
    return liveCoins.find(c => c.symbol === symbol);
  }

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><div className="spinner" /></div>;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em" }}>🪙 إدارة العملات</h1>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--text-secondary)", marginTop: 4 }}>
            <span className="pulse-dot" style={{ background: wsConnected ? "var(--accent-green)" : "var(--accent-red)" }} />
            {wsConnected ? "أسعار حية — تحديث كل 5 ثوان" : "غير متصل"}
          </div>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAdd(!showAdd)}>
          {showAdd ? "✕ إلغاء" : "➕ إضافة عملة"}
        </button>
      </div>

      {msg && (
        <div className="slide-in" style={{
          padding: "12px 18px", marginBottom: 16, borderRadius: 10,
          background: msg.includes("✅") ? "rgba(16,185,129,0.08)" : "rgba(239,68,68,0.08)",
          border: `1px solid ${msg.includes("✅") ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)"}`,
          fontSize: 14,
        }}>{msg}</div>
      )}

      {showAdd && (
        <div className="card slide-in" style={{ padding: 24, marginBottom: 20 }}>
          <h4 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>إضافة عملة يدوياً</h4>
          <form onSubmit={addSymbol} style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>الرمز (مثال: BTCUSDT)</label>
              <input className="form-input" value={form.symbol} onChange={e => setForm({...form, symbol: e.target.value.toUpperCase()})} required style={{ width: 180 }} />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>العملة الأساسية (مثال: BTC)</label>
              <input className="form-input" value={form.base_asset} onChange={e => setForm({...form, base_asset: e.target.value.toUpperCase()})} required style={{ width: 120 }} />
            </div>
            <button type="submit" className="btn btn-primary">إضافة</button>
          </form>
        </div>
      )}

      {/* Suggested Coins */}
      {suggested.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h3 className="section-title">💡 عملات مقترحة (من CoinGecko)</h3>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {suggested.map(coin => (
              <div key={coin.symbol} className="card" style={{
                padding: "14px 18px", display: "flex", alignItems: "center", gap: 14, minWidth: 280, cursor: "pointer",
              }} onClick={() => addSuggested(coin)}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 14 }}>{coin.name}</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{coin.symbol}</div>
                </div>
                <div style={{ marginRight: "auto" }} />
                <div style={{ textAlign: "left" }}>
                  <div style={{ fontWeight: 700, fontSize: 14 }}>${coin.current_price.toLocaleString()}</div>
                  <div style={{ fontSize: 12, color: coin.price_change_24h >= 0 ? "#059669" : "#dc2626", fontWeight: 600 }}>
                    {coin.price_change_24h >= 0 ? "▲" : "▼"} {Math.abs(coin.price_change_24h).toFixed(2)}%
                  </div>
                </div>
                <span style={{ fontSize: 18, color: "var(--accent-blue)" }}>＋</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Current Symbols Table with Live Prices */}
      <div className="card">
        <div style={{ padding: "18px 22px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700 }}>العملات المدعومة ({symbols.length})</h3>
          {wsConnected && <span className="badge badge-green"><span className="pulse-dot" style={{ width: 6, height: 6 }} /> أسعار حية</span>}
        </div>
        <table>
          <thead>
            <tr>
              <th>العملة</th>
              <th>الرمز</th>
              <th>السعر الحالي</th>
              <th>التغيّر 24h</th>
              <th>الحجم 24h</th>
              <th>الحالة</th>
              <th>إجراءات</th>
            </tr>
          </thead>
          <tbody>
            {symbols.map(sym => {
              const live = getLivePrice(sym.symbol);
              const isUp = (live?.change_24h || 0) >= 0;
              return (
                <tr key={sym.id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div style={{
                        width: 32, height: 32, borderRadius: "50%",
                        background: "rgba(59,130,246,0.08)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 12, fontWeight: 800, color: "var(--accent-blue)",
                      }}>{sym.base_asset[0]}</div>
                      <div>
                        <div style={{ fontWeight: 700 }}>{sym.base_asset}</div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{sym.quote_asset}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ fontWeight: 600 }}>{sym.symbol}</td>
                  <td>
                    {live ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span className="pulse-dot" style={{ width: 5, height: 5 }} />
                        <span style={{ fontWeight: 700, fontSize: 14 }}>
                          ${live.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: live.price < 1 ? 6 : 2 })}
                        </span>
                      </div>
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>—</span>
                    )}
                  </td>
                  <td>
                    {live ? (
                      <span style={{ fontWeight: 600, color: isUp ? "#059669" : "#dc2626" }}>
                        {isUp ? "▲" : "▼"} {Math.abs(live.change_24h).toFixed(2)}%
                      </span>
                    ) : "—"}
                  </td>
                  <td>
                    {live ? (
                      <span style={{ fontSize: 13 }}>
                        {live.volume_24h > 1e9 ? `${(live.volume_24h / 1e9).toFixed(1)}B` :
                         live.volume_24h > 1e6 ? `${(live.volume_24h / 1e6).toFixed(1)}M` :
                         live.volume_24h.toLocaleString()}
                      </span>
                    ) : "—"}
                  </td>
                  <td>
                    <span className={`badge ${sym.is_active ? "badge-green" : "badge-red"}`}>
                      {sym.is_active ? "● نشط" : "● معطّل"}
                    </span>
                  </td>
                  <td style={{ display: "flex", gap: 8 }}>
                    <button className="btn btn-ghost" style={{ fontSize: 12, padding: "5px 12px" }}
                      onClick={() => toggleSymbol(sym.id, sym.is_active)}>
                      {sym.is_active ? "إيقاف" : "تفعيل"}
                    </button>
                    <button className="btn btn-danger" style={{ fontSize: 12, padding: "5px 12px" }}
                      onClick={() => deleteSymbol(sym.id)}>حذف</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
