"use client";
import { useEffect, useState } from "react";
import { adminApi, tradeApi } from "@/lib/api";
import type { User, BotSettings } from "@/lib/types";

interface UserWithSettings {
  user: User;
  settings: BotSettings | null;
}

export default function AdminBotSettingsPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      const { data } = await adminApi.getUsers();
      setUsers(data);
    } catch {}
    setLoading(false);
  }

  async function approveAutoTrade(userId: string) {
    try {
      await adminApi.approveAutoTrade(userId);
      loadData();
    } catch {}
  }

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><div className="spinner" /></div>;

  return (
    <div>
      <div className="page-header">
        <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em" }}>🤖 إعدادات البوت</h1>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ padding: "18px 22px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700 }}>موافقات التداول الآلي</h3>
          <span className="badge badge-blue">{users.length} مستخدمين</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>المستخدم</th>
              <th>البريد</th>
              <th>الحالة</th>
              <th>التداول الآلي</th>
              <th>إجراء</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td style={{ fontWeight: 600 }}>{u.username}</td>
                <td style={{ color: "var(--text-secondary)", fontSize: 13 }}>{u.email}</td>
                <td><span className={`badge ${u.is_active ? "badge-green" : "badge-red"}`}>{u.is_active ? "نشط" : "معطّل"}</span></td>
                <td><span className="badge badge-amber">بانتظار التحقق</span></td>
                <td>
                  <button className="btn btn-primary" style={{ fontSize: 12, padding: "6px 16px" }}
                    onClick={() => approveAutoTrade(u.id)}>
                    تبديل الموافقة
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Trading Info Card */}
      <div className="grid-3">
        <div className="card" style={{ padding: 24 }}>
          <h4 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
            <span>🔗</span> ارتباط التحليل بالتداول
          </h4>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.8 }}>
            عند ظهور فرصة من التحليل الآلي، يتم تنفيذ الصفقة مباشرة للمستخدمين المفعّل عندهم التداول الآلي والموافق عليهم من الأدمن.
          </p>
          <div style={{ marginTop: 14, padding: "10px 14px", background: "rgba(59,130,246,0.04)", borderRadius: 10, border: "1px solid var(--border)", fontSize: 12 }}>
            <strong>التسلسل:</strong> تحليل → فرصة → تحقق حدود → تنفيذ → إشعار
          </div>
        </div>

        <div className="card" style={{ padding: 24 }}>
          <h4 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
            <span>🛡️</span> حدود الأمان
          </h4>
          <ul style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 2, paddingRight: 16 }}>
            <li>حد أقصى يومي للصفقات</li>
            <li>حد أقصى لقيمة الصفقة الواحدة</li>
            <li>نسبة محفظة قصوى</li>
            <li>حد أدنى وأعلى للخسارة</li>
            <li>موافقة الأدمن مطلوبة</li>
          </ul>
        </div>

        <div className="card" style={{ padding: 24 }}>
          <h4 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
            <span>📡</span> البث المباشر
          </h4>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.8 }}>
            جميع الصفقات المنفذة تُبث مباشرة عبر WebSocket لجميع المستخدمين المتصلين في صفحة التقارير المباشرة.
          </p>
          <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 8 }}>
            <span className="pulse-dot" />
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>البث نشط</span>
          </div>
        </div>
      </div>
    </div>
  );
}
