"use client";
import { useEffect, useState } from "react";
import { walletApi, tradeApi } from "@/lib/api";
import type { WalletBalance, Trade } from "@/lib/types";

export default function PortfolioPage() {
  const [balances, setBalances] = useState<WalletBalance[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      const [bRes, tRes] = await Promise.all([
        walletApi.getBalance(),
        tradeApi.list(20),
      ]);
      setBalances(bRes.data);
      setTrades(tRes.data);
    } catch (err: any) {
      setError("لم يتم ربط محفظة أو حدث خطأ في جلب البيانات");
    }
    setLoading(false);
  }

  const totalUsd = balances.reduce((sum, w) => sum + w.total_usd, 0);
  const allAssets = balances.flatMap((w) => w.assets);

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><div className="spinner" /></div>;

  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 24, letterSpacing: "-0.02em" }}>💰 محفظتي</h1>

      {/* Portfolio Hero */}
      <div className="card" style={{
        padding: 36, marginBottom: 24,
        background: "linear-gradient(135deg, rgba(59,130,246,0.06), rgba(139,92,246,0.04))",
        border: "1px solid var(--border)",
      }}>
        <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 6, fontWeight: 600 }}>الرصيد الكلي</div>
        <div className="count-up" style={{ fontSize: 42, fontWeight: 800, letterSpacing: "-0.03em", color: "var(--text-primary)" }}>
          ${totalUsd.toLocaleString("en-US", { minimumFractionDigits: 2 })}
        </div>
        {balances.length > 0 && (
          <div style={{ marginTop: 8, fontSize: 13, color: "var(--text-secondary)" }}>
            {balances.map(b => `${b.exchange} (${b.assets.length} عملات)`).join(" · ")}
          </div>
        )}
      </div>

      {/* Assets Grid */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        {allAssets.map((a, i) => (
          <div key={i} className="stat-card" style={{ padding: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <span style={{ fontWeight: 700, fontSize: 15 }}>{a.asset}</span>
              <span className="badge badge-blue">{a.asset}</span>
            </div>
            <div style={{ fontSize: 22, fontWeight: 800 }}>
              ${(a.usd_value || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 6 }}>
              {a.free_balance} متاح · {a.locked_balance} مقفل
            </div>
          </div>
        ))}

        {allAssets.length === 0 && (
          <div className="card empty-state" style={{ gridColumn: "1/-1" }}>
            <div className="empty-state-icon">💼</div>
            <div className="empty-state-title">لم يتم ربط محفظة بعد</div>
            <div className="empty-state-text">اذهب للإعدادات لربط محفظتك بـ Binance أو Bybit</div>
          </div>
        )}
      </div>

      {/* Trade History */}
      <div className="card">
        <div style={{ padding: "18px 22px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700 }}>📜 سجل الصفقات</h3>
          <span className="badge badge-blue">{trades.length} صفقة</span>
        </div>
        {trades.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>لا توجد صفقات بعد</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>التاريخ</th>
                <th>الزوج</th>
                <th>النوع</th>
                <th>الكمية</th>
                <th>السعر</th>
                <th>القيمة</th>
                <th>المنفّذ</th>
                <th>الحالة</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id}>
                  <td style={{ color: "var(--text-secondary)", fontSize: 13 }}>
                    {new Date(t.created_at).toLocaleDateString("ar-EG")} {new Date(t.created_at).toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" })}
                  </td>
                  <td style={{ fontWeight: 600 }}>{t.symbol}</td>
                  <td><span className={`badge ${t.side === "buy" ? "badge-green" : "badge-red"}`}>{t.side === "buy" ? "شراء" : "بيع"}</span></td>
                  <td>{t.quantity}</td>
                  <td>${t.price.toLocaleString()}</td>
                  <td style={{ fontWeight: 600 }}>${t.total_value.toLocaleString()}</td>
                  <td style={{ fontSize: 13 }}>{t.executed_by === "bot" ? "🤖 آلي" : "👤 يدوي"}</td>
                  <td><span className={`badge ${t.status === "filled" ? "badge-green" : t.status === "failed" ? "badge-red" : "badge-amber"}`}>
                    {t.status === "filled" ? "● مكتمل" : t.status === "failed" ? "● فشل" : t.status}
                  </span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
