"use client";
import { useEffect, useState, useRef } from "react";
import { marketApi, WS_BASE } from "@/lib/api";
import type { NewsSource, LiveCoin } from "@/lib/types";

export default function AdminNewsSourcesPage() {
  const [sources, setSources] = useState<NewsSource[]>([]);
  const [suggested, setSuggested] = useState<{name: string; url: string}[]>([]);
  const [liveCoins, setLiveCoins] = useState<LiveCoin[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", url: "" });
  const [editId, setEditId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ name: "", url: "" });
  const [msg, setMsg] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => { loadData(); connectWS(); return () => { if (wsRef.current) wsRef.current.close(); }; }, []);

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
      const [sRes, sgRes] = await Promise.all([
        marketApi.getNewsSources(),
        marketApi.getSuggestedSources(),
      ]);
      setSources(sRes.data);
      setSuggested(sgRes.data);
    } catch {}
    setLoading(false);
  }

  async function addSource(e: React.FormEvent) {
    e.preventDefault();
    try {
      await marketApi.addNewsSource({ name: form.name, url: form.url });
      setMsg("✅ تم إضافة المصدر");
      setShowAdd(false);
      setForm({ name: "", url: "" });
      loadData();
    } catch (err: any) {
      setMsg(`❌ ${err.response?.data?.detail || "فشل"}`);
    }
    setTimeout(() => setMsg(""), 3000);
  }

  async function addSuggested(s: {name: string; url: string}) {
    try {
      await marketApi.addNewsSource({ name: s.name, url: s.url });
      setMsg(`✅ تم إضافة ${s.name}`);
      loadData();
    } catch (err: any) {
      setMsg(`❌ ${err.response?.data?.detail || "فشل"}`);
    }
    setTimeout(() => setMsg(""), 3000);
  }

  async function toggleSource(id: string, currentActive: boolean) {
    try {
      await marketApi.updateNewsSource(id, { is_active: !currentActive });
      loadData();
    } catch {}
  }

  async function saveEdit(id: string) {
    try {
      await marketApi.updateNewsSource(id, editForm);
      setEditId(null);
      loadData();
    } catch {}
  }

  async function deleteSource(id: string) {
    if (!confirm("هل أنت متأكد من حذف هذا المصدر؟")) return;
    try {
      await marketApi.deleteNewsSource(id);
      loadData();
    } catch {}
  }

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><div className="spinner" /></div>;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em" }}>📰 مصادر الأخبار الموثوقة</h1>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--text-secondary)", marginTop: 4 }}>
            <span className="pulse-dot" style={{ background: wsConnected ? "var(--accent-green)" : "var(--accent-red)" }} />
            {wsConnected ? "أسعار حية" : "غير متصل"}
          </div>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAdd(!showAdd)}>
          {showAdd ? "✕ إلغاء" : "➕ إضافة مصدر"}
        </button>
      </div>

      {/* Live Price Ticker */}
      {liveCoins.length > 0 && (
        <div style={{ display: "flex", gap: 10, overflowX: "auto", marginBottom: 20, paddingBottom: 4, scrollbarWidth: "none" }}>
          {liveCoins.slice(0, 8).map(coin => {
            const isUp = coin.change_24h >= 0;
            return (
              <div key={coin.symbol} style={{
                display: "flex", alignItems: "center", gap: 10, padding: "10px 16px",
                background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 10,
                flexShrink: 0, minWidth: 160,
              }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 13 }}>{coin.base_asset}</div>
                  <div style={{ fontWeight: 800, fontSize: 14 }}>
                    ${coin.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: coin.price < 1 ? 4 : 2 })}
                  </div>
                </div>
                <span style={{ fontSize: 12, fontWeight: 600, color: isUp ? "#059669" : "#dc2626" }}>
                  {isUp ? "▲" : "▼"}{Math.abs(coin.change_24h).toFixed(2)}%
                </span>
                <span className="pulse-dot" style={{ width: 5, height: 5 }} />
              </div>
            );
          })}
        </div>
      )}

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
          <h4 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>إضافة مصدر جديد</h4>
          <form onSubmit={addSource} style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>اسم المصدر</label>
              <input className="form-input" value={form.name} onChange={e => setForm({...form, name: e.target.value})} required style={{ width: 220 }} />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>الرابط (اختياري)</label>
              <input className="form-input" value={form.url} onChange={e => setForm({...form, url: e.target.value})} style={{ width: 300 }} placeholder="https://..." />
            </div>
            <button type="submit" className="btn btn-primary">إضافة</button>
          </form>
        </div>
      )}

      {/* Suggested Sources */}
      {suggested.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h3 className="section-title">💡 مصادر مقترحة</h3>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {suggested.map(s => (
              <div key={s.name} className="card" style={{
                padding: "12px 18px", display: "flex", alignItems: "center", gap: 12, cursor: "pointer",
              }} onClick={() => addSuggested(s)}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 14 }}>{s.name}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{s.url}</div>
                </div>
                <span style={{ fontSize: 18, color: "var(--accent-blue)" }}>＋</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Current Sources */}
      <div className="card">
        <div style={{ padding: "18px 22px", borderBottom: "1px solid var(--border)" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700 }}>المصادر المضافة ({sources.length})</h3>
        </div>
        <table>
          <thead>
            <tr>
              <th>المصدر</th>
              <th>الرابط</th>
              <th>النوع</th>
              <th>الحالة</th>
              <th>إجراءات</th>
            </tr>
          </thead>
          <tbody>
            {sources.map(src => (
              <tr key={src.id}>
                <td>
                  {editId === src.id ? (
                    <input className="form-input" value={editForm.name} onChange={e => setEditForm({...editForm, name: e.target.value})} style={{ width: 180, padding: "6px 10px" }} />
                  ) : (
                    <span style={{ fontWeight: 700 }}>{src.name}</span>
                  )}
                </td>
                <td>
                  {editId === src.id ? (
                    <input className="form-input" value={editForm.url} onChange={e => setEditForm({...editForm, url: e.target.value})} style={{ width: 250, padding: "6px 10px" }} />
                  ) : (
                    <a href={src.url || "#"} target="_blank" style={{ color: "var(--accent-blue)", fontSize: 13 }}>{src.url || "—"}</a>
                  )}
                </td>
                <td>
                  {src.is_suggested ? <span className="badge badge-purple">مقترح</span> : <span className="badge badge-blue">مخصص</span>}
                </td>
                <td>
                  <span className={`badge ${src.is_active ? "badge-green" : "badge-red"}`}>
                    {src.is_active ? "● نشط" : "● معطّل"}
                  </span>
                </td>
                <td style={{ display: "flex", gap: 6 }}>
                  {editId === src.id ? (
                    <>
                      <button className="btn btn-primary" style={{ fontSize: 12, padding: "5px 12px" }} onClick={() => saveEdit(src.id)}>حفظ</button>
                      <button className="btn btn-ghost" style={{ fontSize: 12, padding: "5px 12px" }} onClick={() => setEditId(null)}>إلغاء</button>
                    </>
                  ) : (
                    <>
                      <button className="btn btn-ghost" style={{ fontSize: 12, padding: "5px 12px" }} onClick={() => { setEditId(src.id); setEditForm({ name: src.name, url: src.url || "" }); }}>تعديل</button>
                      <button className="btn btn-ghost" style={{ fontSize: 12, padding: "5px 12px" }} onClick={() => toggleSource(src.id, src.is_active)}>
                        {src.is_active ? "إيقاف" : "تفعيل"}
                      </button>
                      <button className="btn btn-danger" style={{ fontSize: 12, padding: "5px 12px" }} onClick={() => deleteSource(src.id)}>حذف</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
