"use client";
import { useEffect, useState } from "react";
import { adminApi, walletApi } from "@/lib/api";
import type { User } from "@/lib/types";

export default function AdminWalletsPage() {
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

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><div className="spinner" /></div>;

  return (
    <div>
      <div className="page-header">
        <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em" }}>💼 مراقبة المحافظ</h1>
      </div>

      <div className="card">
        <div style={{ padding: "18px 22px", borderBottom: "1px solid var(--border)" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700 }}>المستخدمين والمحافظ</h3>
        </div>
        <table>
          <thead>
            <tr>
              <th>المستخدم</th>
              <th>البريد</th>
              <th>الحالة</th>
              <th>تاريخ الانضمام</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td style={{ fontWeight: 600 }}>{u.username}</td>
                <td style={{ color: "var(--text-secondary)", fontSize: 13 }}>{u.email}</td>
                <td><span className={`badge ${u.is_active ? "badge-green" : "badge-red"}`}>{u.is_active ? "● نشط" : "● معطّل"}</span></td>
                <td style={{ color: "var(--text-muted)", fontSize: 13 }}>{new Date(u.created_at).toLocaleDateString("ar-EG")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
