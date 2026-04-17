"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { data } = await authApi.login(email, password);
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("refresh_token", data.refresh_token);
      router.push("/dashboard");
    } catch (err: any) {
      setError(err.response?.data?.detail || "خطأ في تسجيل الدخول");
    }
    setLoading(false);
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "linear-gradient(135deg, #e8ecf6 0%, #dde3f0 50%, #e4e9f7 100%)",
    }}>
      <div style={{
        width: 420,
        background: "rgba(255, 255, 255, 0.9)",
        border: "1px solid rgba(59, 130, 246, 0.1)",
        borderRadius: 20,
        padding: 44,
        backdropFilter: "blur(20px)",
        boxShadow: "0 20px 60px rgba(0,0,0,0.08), 0 4px 16px rgba(0,0,0,0.04)",
      }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: 36 }}>
          <div style={{
            width: 60, height: 60,
            background: "var(--gradient-primary)",
            borderRadius: 16,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 24, fontWeight: 800, color: "#fff",
            marginBottom: 18,
            boxShadow: "0 4px 20px rgba(59,130,246,0.3)",
          }}>CA</div>
          <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 6, color: "#1a1d2e", letterSpacing: "-0.02em" }}>CryptoAnalyzer</h1>
          <p style={{ color: "#8e95ab", fontSize: 14 }}>منصة تحليل العملات الرقمية</p>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 20 }}>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#5a6178", marginBottom: 8 }}>
              البريد الإلكتروني
            </label>
            <input
              className="form-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@cryptoanalyzer.local"
              required
            />
          </div>
          <div style={{ marginBottom: 28 }}>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#5a6178", marginBottom: 8 }}>
              كلمة المرور
            </label>
            <input
              className="form-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>

          {error && (
            <div style={{
              background: "rgba(239,68,68,0.06)",
              border: "1px solid rgba(239,68,68,0.15)",
              borderRadius: 10,
              padding: "12px 16px",
              marginBottom: 18,
              fontSize: 13,
              color: "#dc2626",
              fontWeight: 500,
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading}
            style={{ width: "100%", justifyContent: "center", padding: "13px 0", fontSize: 15, borderRadius: 12 }}
          >
            {loading ? "جارٍ الدخول..." : "تسجيل الدخول"}
          </button>
        </form>

        <p style={{ textAlign: "center", marginTop: 22, fontSize: 12, color: "#8e95ab" }}>
          الوصول بدعوة من الأدمن فقط
        </p>
      </div>
    </div>
  );
}
