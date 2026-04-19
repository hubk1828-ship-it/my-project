import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

// Interceptor: add JWT token to every request
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Interceptor: auto-refresh on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const refreshToken = localStorage.getItem("refresh_token");
        if (refreshToken) {
          const { data } = await axios.post(`${API_BASE}/api/auth/refresh`, {
            refresh_token: refreshToken,
          });
          localStorage.setItem("access_token", data.access_token);
          localStorage.setItem("refresh_token", data.refresh_token);
          originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
          return api(originalRequest);
        }
      } catch {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default api;

// ===== Auth =====
export const authApi = {
  login: (email: string, password: string) =>
    api.post("/api/auth/login", { email, password }),
  refresh: (refresh_token: string) =>
    api.post("/api/auth/refresh", { refresh_token }),
};

// ===== Admin =====
export const adminApi = {
  getUsers: () => api.get("/api/admin/users"),
  createUser: (data: { username: string; email: string; password: string; role?: string }) =>
    api.post("/api/admin/users", data),
  toggleUser: (userId: string) => api.patch(`/api/admin/users/${userId}/toggle`),
  approveAutoTrade: (userId: string) =>
    api.patch(`/api/admin/users/${userId}/approve-auto-trade`),
  runAnalysis: () => api.post("/api/admin/run-analysis"),
};

// ===== Wallets =====
export const walletApi = {
  list: () => api.get("/api/wallets/"),
  connect: (data: { exchange: string; api_key: string; api_secret: string; label?: string }) =>
    api.post("/api/wallets/connect", data),
  disconnect: (walletId: string) => api.delete(`/api/wallets/disconnect/${walletId}`),
  getBalance: () => api.get("/api/wallets/balance"),
};

// ===== Analysis =====
export const analysisApi = {
  getToday: () => api.get("/api/analysis/today"),
  getHistory: (symbol?: string, limit?: number) =>
    api.get("/api/analysis/history", { params: { symbol, limit } }),
  liveAnalysis: (symbol: string, timeframe: string) =>
    api.get("/api/analysis/live", { params: { symbol, timeframe } }),
  clearAll: () => api.delete("/api/analysis/clear"),
};

// ===== Trades =====
export const tradeApi = {
  list: (limit?: number) => api.get("/api/trades", { params: { limit } }),
  getBotSettings: () => api.get("/api/settings/bot"),
  toggleAutoTrade: (enabled: boolean) =>
    api.patch("/api/settings/auto-trade", { is_auto_trade_enabled: enabled }),
  updateLimits: (data: Record<string, number>) =>
    api.patch("/api/settings/limits", data),
};

// ===== Notifications =====
export const notificationApi = {
  list: () => api.get("/api/notifications/"),
  markRead: (id: string) => api.patch(`/api/notifications/${id}/read`),
  getPreferences: () => api.get("/api/notifications/preferences"),
  updatePreferences: (data: Record<string, any>) =>
    api.patch("/api/notifications/preferences", data),
};

// ===== Market (News Sources & Symbols) =====
export const marketApi = {
  // News sources
  getNewsSources: () => api.get("/api/market/news-sources"),
  getSuggestedSources: () => api.get("/api/market/news-sources/suggestions"),
  addNewsSource: (data: { name: string; url?: string; is_active?: boolean }) =>
    api.post("/api/market/news-sources", data),
  updateNewsSource: (id: string, data: { name?: string; url?: string; is_active?: boolean }) =>
    api.patch(`/api/market/news-sources/${id}`, data),
  deleteNewsSource: (id: string) => api.delete(`/api/market/news-sources/${id}`),

  // Symbols
  getSymbols: () => api.get("/api/market/symbols"),
  addSymbol: (data: { symbol: string; base_asset: string; quote_asset?: string; is_default?: boolean }) =>
    api.post("/api/market/symbols", data),
  updateSymbol: (id: string, data: { is_active?: boolean; is_default?: boolean }) =>
    api.patch(`/api/market/symbols/${id}`, data),
  deleteSymbol: (id: string) => api.delete(`/api/market/symbols/${id}`),

  // Suggested coins
  getSuggestedCoins: () => api.get("/api/market/suggested-coins"),
};

// ===== Paper Trading =====
export const paperApi = {
  // Wallet
  getWallet: () => api.get("/api/paper/wallet"),
  createWallet: (data: { initial_balance: number; label?: string }) =>
    api.post("/api/paper/wallet", data),
  deleteWallet: () => api.delete("/api/paper/wallet"),
  resetWallet: (data: { initial_balance: number; label?: string }) =>
    api.post("/api/paper/wallet/reset", data),

  // Trades
  executeTrade: (data: { symbol: string; side: string; amount_usdt: number }) =>
    api.post("/api/paper/trade", data),
  getTrades: (limit?: number) => api.get("/api/paper/trades", { params: { limit } }),

  // Bot Settings
  getBotSettings: () => api.get("/api/paper/bot-settings"),
  updateBotSettings: (data: Record<string, any>) =>
    api.patch("/api/paper/bot-settings", data),

  // Signals
  getSignals: (params?: { status?: string; timeframe_type?: string; symbol?: string }) =>
    api.get("/api/paper/signals", { params }),
  getActiveSignals: () => api.get("/api/paper/signals/active"),
  generateSignals: (timeframe?: string) =>
    api.post(`/api/paper/signals/generate?timeframe=${timeframe || "1h"}`),
  getSignalPerformance: (symbol?: string) =>
    api.get("/api/paper/signals/performance", { params: { symbol } }),
  getSignalHistory: (symbol: string) =>
    api.get(`/api/paper/signals/history/${symbol}`),
  getBotAnalysis: () => api.get("/api/paper/signals/bot-analysis"),
  resetSignals: () => api.delete("/api/paper/signals/reset"),
};

// ===== WebSocket URL =====
export const WS_BASE = API_BASE.replace("http", "ws");
