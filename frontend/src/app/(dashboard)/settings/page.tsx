"use client";
import { useEffect, useState } from "react";
import { walletApi, tradeApi, notificationApi } from "@/lib/api";
import type { BotSettings, NotificationPrefs } from "@/lib/types";

export default function SettingsPage() {
  const [exchange, setExchange] = useState("binance");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [walletMsg, setWalletMsg] = useState("");
  const [botSettings, setBotSettings] = useState<BotSettings | null>(null);
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null);
  const [chatId, setChatId] = useState("");
  const [saveMsg, setSaveMsg] = useState("");

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      const [bRes, pRes] = await Promise.all([
        tradeApi.getBotSettings(),
        notificationApi.getPreferences(),
      ]);
      setBotSettings(bRes.data);
      setPrefs(pRes.data);
      setChatId(pRes.data.telegram_chat_id || "");
    } catch {}
  }

  async function connectWallet(e: React.FormEvent) {
    e.preventDefault();
    setWalletMsg("");
    try {
      await walletApi.connect({ exchange, api_key: apiKey, api_secret: apiSecret });
      setWalletMsg("✅ تم ربط المحفظة بنجاح");
      setApiKey(""); setApiSecret("");
    } catch (err: any) {
      setWalletMsg(`❌ ${err.response?.data?.detail || "فشل الربط"}`);
    }
  }

  async function toggleAutoTrade() {
    if (!botSettings) return;
    try {
      await tradeApi.toggleAutoTrade(!botSettings.is_auto_trade_enabled);
      loadData();
    } catch {}
  }

  async function saveLimits(e: React.FormEvent) {
    e.preventDefault();
    if (!botSettings) return;
    try {
      await tradeApi.updateLimits({
        max_trades_per_day: botSettings.max_trades_per_day,
        max_trade_amount: botSettings.max_trade_amount,
        max_portfolio_percentage: botSettings.max_portfolio_percentage,
        max_daily_loss: botSettings.max_daily_loss,
        min_loss_limit: botSettings.min_loss_limit,
        max_loss_limit: botSettings.max_loss_limit,
      });
      setSaveMsg("✅ تم حفظ الحدود");
      setTimeout(() => setSaveMsg(""), 3000);
    } catch (err: any) {
      setSaveMsg(`❌ ${err.response?.data?.detail || "فشل الحفظ"}`);
    }
  }

  async function saveNotifPrefs() {
    try {
      await notificationApi.updatePreferences({
        telegram_chat_id: chatId,
        ...prefs,
      });
      setSaveMsg("✅ تم حفظ إعدادات التنبيهات");
      setTimeout(() => setSaveMsg(""), 3000);
    } catch (err: any) {
      setSaveMsg(`❌ ${err.response?.data?.detail || "فشل الحفظ"}`);
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 24, letterSpacing: "-0.02em" }}>⚙️ الإعدادات</h1>

      {saveMsg && (
        <div className="slide-in" style={{
          padding: "12px 18px", marginBottom: 16, borderRadius: 10,
          background: saveMsg.includes("✅") ? "rgba(16,185,129,0.08)" : "rgba(239,68,68,0.08)",
          border: `1px solid ${saveMsg.includes("✅") ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)"}`,
          fontSize: 14, fontWeight: 500,
        }}>{saveMsg}</div>
      )}

      <div className="grid-2">
        {/* Wallet Connection */}
        <div className="card" style={{ padding: 24 }}>
          <h4 style={{ fontSize: 16, fontWeight: 700, marginBottom: 20, display: "flex", alignItems: "center", gap: 8 }}>
            <span>🔗</span> ربط المنصة
          </h4>
          <form onSubmit={connectWallet}>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>المنصة</label>
              <select className="form-input" value={exchange} onChange={(e) => setExchange(e.target.value)}>
                <option value="binance">Binance</option>
                <option value="bybit">Bybit</option>
              </select>
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>API Key</label>
              <input className="form-input" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="أدخل مفتاح API" />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>API Secret</label>
              <input className="form-input" type="password" value={apiSecret} onChange={(e) => setApiSecret(e.target.value)} placeholder="أدخل السر" />
            </div>
            <button type="submit" className="btn btn-primary">ربط المحفظة</button>
            {walletMsg && <p style={{ marginTop: 12, fontSize: 13, fontWeight: 500 }}>{walletMsg}</p>}
          </form>
        </div>

        {/* Auto Trade Settings */}
        <div className="card" style={{ padding: 24 }}>
          <h4 style={{ fontSize: 16, fontWeight: 700, marginBottom: 20, display: "flex", alignItems: "center", gap: 8 }}>
            <span>🤖</span> التداول الآلي
          </h4>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 0", borderBottom: "1px solid var(--border)" }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>تفعيل التداول الآلي</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>يحتاج موافقة الأدمن</div>
            </div>
            <label className="toggle">
              <input type="checkbox" checked={botSettings?.is_auto_trade_enabled || false} onChange={toggleAutoTrade} />
              <span className="toggle-slider" />
            </label>
          </div>
          {botSettings && !botSettings.is_admin_approved && (
            <div style={{ marginTop: 12, padding: "10px 14px", background: "rgba(245,158,11,0.06)", borderRadius: 10, fontSize: 13, color: "#d97706", fontWeight: 500, border: "1px solid rgba(245,158,11,0.12)" }}>
              ⚠️ بانتظار موافقة الأدمن
            </div>
          )}
          <form onSubmit={saveLimits} style={{ marginTop: 18 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>الحد الأقصى للعمليات اليومية</label>
                <input className="form-input" type="number" value={botSettings?.max_trades_per_day || 5}
                  onChange={(e) => setBotSettings(s => s ? {...s, max_trades_per_day: +e.target.value} : s)} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>الحد الأقصى للصفقة (USDT)</label>
                <input className="form-input" type="number" value={botSettings?.max_trade_amount || 100}
                  onChange={(e) => setBotSettings(s => s ? {...s, max_trade_amount: +e.target.value} : s)} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>نسبة المحفظة القصوى (%)</label>
                <input className="form-input" type="number" value={botSettings?.max_portfolio_percentage || 10}
                  onChange={(e) => setBotSettings(s => s ? {...s, max_portfolio_percentage: +e.target.value} : s)} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>الخسارة اليومية القصوى (USDT)</label>
                <input className="form-input" type="number" value={botSettings?.max_daily_loss || 50}
                  onChange={(e) => setBotSettings(s => s ? {...s, max_daily_loss: +e.target.value} : s)} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>
                  الحد الأدنى للخسارة (USDT)
                  <span style={{ color: "var(--accent-amber)", marginRight: 4 }}>*جديد</span>
                </label>
                <input className="form-input" type="number" value={botSettings?.min_loss_limit || 10}
                  onChange={(e) => setBotSettings(s => s ? {...s, min_loss_limit: +e.target.value} : s)} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>
                  الحد الأعلى للخسارة (USDT)
                  <span style={{ color: "var(--accent-amber)", marginRight: 4 }}>*جديد</span>
                </label>
                <input className="form-input" type="number" value={botSettings?.max_loss_limit || 200}
                  onChange={(e) => setBotSettings(s => s ? {...s, max_loss_limit: +e.target.value} : s)} />
              </div>
            </div>
            <button type="submit" className="btn btn-primary" style={{ marginTop: 16 }}>حفظ الحدود</button>
          </form>
        </div>

        {/* Notifications */}
        <div className="card" style={{ padding: 24 }}>
          <h4 style={{ fontSize: 16, fontWeight: 700, marginBottom: 20, display: "flex", alignItems: "center", gap: 8 }}>
            <span>🔔</span> التنبيهات
          </h4>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>Telegram Chat ID</label>
            <input className="form-input" value={chatId} onChange={(e) => setChatId(e.target.value)} placeholder="أدخل Chat ID" />
          </div>
          {prefs && (
            <>
              {[
                { key: "notify_opportunities", label: "تنبيهات الفرص", icon: "📈" },
                { key: "notify_trades", label: "تنبيهات الصفقات", icon: "💰" },
                { key: "notify_daily_summary", label: "ملخص يومي", icon: "📊" },
              ].map(({ key, label, icon }) => (
                <div key={key} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderBottom: "1px solid var(--border)" }}>
                  <span style={{ fontSize: 14, display: "flex", alignItems: "center", gap: 8 }}>
                    <span>{icon}</span> {label}
                  </span>
                  <label className="toggle">
                    <input type="checkbox" checked={(prefs as any)[key]}
                      onChange={() => setPrefs(p => p ? {...p, [key]: !(p as any)[key]} : p)} />
                    <span className="toggle-slider" />
                  </label>
                </div>
              ))}
            </>
          )}
          <button onClick={saveNotifPrefs} className="btn btn-primary" style={{ marginTop: 18 }}>حفظ التنبيهات</button>
        </div>
      </div>
    </div>
  );
}
