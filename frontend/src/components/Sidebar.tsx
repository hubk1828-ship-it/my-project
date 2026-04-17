"use client";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

interface NavItem {
  label: string;
  icon: string;
  href: string;
}

const userNav: NavItem[] = [
  { label: "التقارير المباشرة", icon: "📡", href: "/dashboard" },
  { label: "التحليل اليومي", icon: "📊", href: "/reports" },
  { label: "محفظتي", icon: "💰", href: "/portfolio" },
  { label: "الإعدادات", icon: "⚙️", href: "/settings" },
];

const adminNav: NavItem[] = [
  { label: "إدارة المستخدمين", icon: "👥", href: "/admin/users" },
  { label: "إدارة العملات", icon: "🪙", href: "/admin/symbols" },
  { label: "مصادر الأخبار", icon: "📰", href: "/admin/news-sources" },
  { label: "إعدادات البوت", icon: "🤖", href: "/admin/bot-settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [role, setRole] = useState<string>("user");
  const [username, setUsername] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) {
      try {
        const payload = JSON.parse(atob(token.split(".")[1]));
        setRole(payload.role || "user");
        setUsername(payload.role === "admin" ? "أدمن" : "مستخدم");
      } catch {}
    }
  }, []);

  function handleLogout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    router.push("/login");
  }

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div style={{
        padding: "22px 24px",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        gap: 12,
      }}>
        <div style={{
          width: 40, height: 40,
          background: "var(--gradient-primary)",
          borderRadius: 12,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 16, fontWeight: 800, color: "#fff",
          boxShadow: "0 2px 12px rgba(59,130,246,0.3)",
        }}>CA</div>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, background: "var(--gradient-primary)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            CryptoAnalyzer
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>v2.0 — منصة تحليل داخلية</div>
        </div>
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, padding: "12px", overflowY: "auto" }}>
        {role === "admin" && (
          <div style={{ padding: "14px 14px 6px", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1.5, color: "var(--text-muted)" }}>
            لوحة الأدمن
          </div>
        )}
        {(role === "admin" ? adminNav : []).map((item) => (
          <div
            key={item.href}
            className={`nav-item ${pathname === item.href ? "active" : ""}`}
            onClick={() => router.push(item.href)}
          >
            <span style={{ fontSize: 18, width: 24, textAlign: "center" }}>{item.icon}</span>
            {item.label}
          </div>
        ))}

        <div style={{ padding: "16px 14px 6px", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1.5, color: "var(--text-muted)" }}>
          {role === "admin" ? "عام" : "القائمة"}
        </div>
        {userNav.map((item) => (
          <div
            key={item.href}
            className={`nav-item ${pathname === item.href ? "active" : ""}`}
            onClick={() => router.push(item.href)}
          >
            <span style={{ fontSize: 18, width: 24, textAlign: "center" }}>{item.icon}</span>
            {item.label}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div style={{ padding: 16, borderTop: "1px solid var(--border)" }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "12px 14px",
          background: "rgba(59,130,246,0.04)",
          borderRadius: 10,
          border: "1px solid var(--border)",
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: "50%",
            background: "var(--gradient-primary)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 13, fontWeight: 700, color: "#fff",
            boxShadow: "0 2px 8px rgba(59,130,246,0.2)",
          }}>{role === "admin" ? "A" : "U"}</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{username}</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{role === "admin" ? "مدير النظام" : "مستخدم عادي"}</div>
          </div>
          <button
            onClick={handleLogout}
            style={{
              background: "none", border: "none", color: "var(--text-muted)",
              cursor: "pointer", fontSize: 16, padding: 4,
              transition: "color 0.2s",
            }}
            title="تسجيل الخروج"
          >🚪</button>
        </div>
      </div>
    </aside>
  );
}
