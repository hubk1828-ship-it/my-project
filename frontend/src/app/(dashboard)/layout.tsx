"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) router.push("/login");
  }, [router]);

  return (
    <>
      <Sidebar />
      <header className="topbar">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className="page-title">CryptoAnalyzer</span>
          <span className="pulse-dot" title="متصل" />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            background: "var(--bg-primary)",
            border: "1px solid var(--border)",
            borderRadius: 10,
            padding: "9px 16px",
          }}>
            <span style={{ color: "var(--text-muted)" }}>🔍</span>
            <input
              type="text"
              placeholder="بحث..."
              style={{
                background: "none", border: "none", outline: "none",
                color: "var(--text-primary)", fontSize: 13, width: 200,
                fontFamily: "inherit",
              }}
            />
          </div>
        </div>
      </header>
      <main className="main-content animate-in">
        {children}
      </main>
    </>
  );
}
