"use client";
import { useEffect, useState } from "react";
import { adminApi } from "@/lib/api";
import type { User } from "@/lib/types";

export default function AdminUsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ username: "", email: "", password: "", role: "user" });
  const [msg, setMsg] = useState("");

  useEffect(() => { loadUsers(); }, []);

  async function loadUsers() {
    try {
      const { data } = await adminApi.getUsers();
      setUsers(data);
    } catch {}
    setLoading(false);
  }

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setMsg("");
    try {
      await adminApi.createUser(form);
      setMsg("✅ تم إنشاء المستخدم");
      setShowCreate(false);
      setForm({ username: "", email: "", password: "", role: "user" });
      loadUsers();
    } catch (err: any) {
      setMsg(`❌ ${err.response?.data?.detail || "فشل الإنشاء"}`);
    }
  }

  async function toggleUser(userId: string) {
    try {
      await adminApi.toggleUser(userId);
      loadUsers();
    } catch {}
  }

  async function approveAutoTrade(userId: string) {
    try {
      await adminApi.approveAutoTrade(userId);
      loadUsers();
    } catch {}
  }

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><div className="spinner" /></div>;

  return (
    <div>
      <div className="page-header">
        <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em" }}>👥 إدارة المستخدمين</h1>
        <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? "✕ إلغاء" : "➕ مستخدم جديد"}
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

      {showCreate && (
        <div className="card slide-in" style={{ padding: 24, marginBottom: 20 }}>
          <h4 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>إنشاء مستخدم جديد</h4>
          <form onSubmit={createUser} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>اسم المستخدم</label>
              <input className="form-input" value={form.username} onChange={e => setForm({...form, username: e.target.value})} required />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>البريد الإلكتروني</label>
              <input className="form-input" type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} required />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>كلمة المرور</label>
              <input className="form-input" type="password" value={form.password} onChange={e => setForm({...form, password: e.target.value})} required />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>الدور</label>
              <select className="form-input" value={form.role} onChange={e => setForm({...form, role: e.target.value})}>
                <option value="user">مستخدم</option>
                <option value="admin">أدمن</option>
              </select>
            </div>
            <div style={{ gridColumn: "1/-1" }}>
              <button type="submit" className="btn btn-primary">إنشاء</button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>المستخدم</th>
              <th>البريد</th>
              <th>الدور</th>
              <th>الحالة</th>
              <th>التداول الآلي</th>
              <th>تاريخ الإنشاء</th>
              <th>إجراءات</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td style={{ fontWeight: 600 }}>{u.username}</td>
                <td style={{ color: "var(--text-secondary)", fontSize: 13 }}>{u.email}</td>
                <td><span className={`badge ${u.role === "admin" ? "badge-purple" : "badge-blue"}`}>{u.role === "admin" ? "أدمن" : "مستخدم"}</span></td>
                <td><span className={`badge ${u.is_active ? "badge-green" : "badge-red"}`}>{u.is_active ? "● نشط" : "● معطّل"}</span></td>
                <td>
                  <button className="btn btn-ghost" style={{ fontSize: 12, padding: "5px 12px" }} onClick={() => approveAutoTrade(u.id)}>
                    موافقة
                  </button>
                </td>
                <td style={{ color: "var(--text-muted)", fontSize: 13 }}>{new Date(u.created_at).toLocaleDateString("ar-EG")}</td>
                <td>
                  <button className={`btn ${u.is_active ? "btn-danger" : "btn-success"}`} style={{ fontSize: 12, padding: "5px 12px" }} onClick={() => toggleUser(u.id)}>
                    {u.is_active ? "تعطيل" : "تفعيل"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
