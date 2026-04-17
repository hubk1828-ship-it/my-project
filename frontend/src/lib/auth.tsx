"use client";
import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import type { User } from "@/lib/types";
import api from "@/lib/api";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextType>({} as AuthContextType);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    checkAuth();
  }, []);

  async function checkAuth() {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      // Decode JWT payload to get user info
      const payload = JSON.parse(atob(token.split(".")[1]));
      const isAdmin = payload.role === "admin";

      if (isAdmin) {
        // Admin can fetch user list to find themselves
        try {
          const { data } = await api.get("/api/admin/users");
          const currentUser = (data as User[]).find((u: User) => u.id === payload.sub);
          if (currentUser) {
            setUser(currentUser);
            setLoading(false);
            return;
          }
        } catch {}
      }

      // Fallback: construct user from token payload
      setUser({
        id: payload.sub,
        role: payload.role || "user",
        username: "",
        email: "",
        is_active: true,
        created_at: "",
        updated_at: "",
      });
    } catch {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    }
    setLoading(false);
  }

  async function login(email: string, password: string) {
    const { data } = await authApi.login(email, password);
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    await checkAuth();
    router.push("/dashboard");
  }

  function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setUser(null);
    router.push("/login");
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, isAdmin: user?.role === "admin" }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
