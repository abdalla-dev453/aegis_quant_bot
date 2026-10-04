/**
 * AegisQuant API Client (Pure JavaScript / JSX compatible)
 * Interacts with FastAPI /app/v1/* and /ea/v1/* surfaces
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/app/v1";

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const defaultHeaders = {
    "Content-Type": "application/json",
  };

  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
    credentials: "include", // for session cookies
  };

  if (options.body && typeof options.body === "object") {
    config.body = JSON.stringify(options.body);
  }

  try {
    const res = await fetch(url, config);
    if (!res.ok) {
      let errData;
      try {
        errData = await res.json();
      } catch {
        errData = { code: "HTTP_ERROR", message: `Request failed with status ${res.status}` };
      }
      const error = new Error(errData.message || "An unexpected error occurred");
      error.code = errData.code;
      error.details = errData.details;
      error.status = res.status;
      throw error;
    }
    if (res.status === 204) return null;
    return await res.json();
  } catch (err) {
    console.warn(`[API] ${options.method || "GET"} ${path} failed:`, err.message);
    throw err;
  }
}

export const api = {
  // Auth
  signup: (email, password, risk_disclaimer_accepted) =>
    request("/auth/signup", { method: "POST", body: { email, password, risk_disclaimer_accepted } }),
  login: (email, password) =>
    request("/auth/login", { method: "POST", body: { email, password } }),
  getMe: () => request("/auth/me"),
  logout: () => request("/auth/logout", { method: "POST" }),

  // Devices & Pairing
  createPairingCode: () => request("/devices/pairing-codes", { method: "POST" }),
  getDevices: () => request("/devices"),
  renameDevice: (deviceId, name) => request(`/devices/${deviceId}`, { method: "PATCH", body: { name } }),
  revokeDevice: (deviceId) => request(`/devices/${deviceId}`, { method: "DELETE" }),

  // Dashboard & Telemetry
  getDashboard: () => request("/dashboard"),
  getAccountOverview: (deviceId) => request(`/accounts/${deviceId}/overview`),
  getPositions: (deviceId) => request(`/accounts/${deviceId}/positions`),
  getEquityCurve: (deviceId, range = "7d") => request(`/accounts/${deviceId}/equity-curve?range=${range}`),

  // Signals
  getSignals: (deviceId, status) => {
    const params = new URLSearchParams();
    if (deviceId) params.append("device_id", deviceId);
    if (status) params.append("status", status);
    const query = params.toString() ? `?${params.toString()}` : "";
    return request(`/signals${query}`);
  },
  getSignalDetail: (signalId) => request(`/signals/${signalId}`),
  dispatchSignal: (deviceId, symbol = "EURUSD", action = "BUY", price = "1.08500") =>
    request(`/devices/${deviceId}/dispatch-signal?symbol=${symbol}&action=${action}&price=${price}`, {
      method: "POST",
    }),

  // Risk & Kill Switch
  updateRiskProfile: (deviceId, profile) =>
    request(`/risk-profile/${deviceId}`, { method: "PATCH", body: profile }),
  triggerKillSwitch: () => request("/kill-switch", { method: "POST" }),

  // Journal & Analytics
  getJournalMetrics: () => request("/journal/metrics"),
  getJournalHeatmap: () => request("/journal/heatmap"),
};
