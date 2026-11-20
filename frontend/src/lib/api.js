const BASE = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const TOKEN_KEY = "sg_token";

// The token lives in localStorage so a refresh keeps you signed in. Trade-off: any script running
// on this page could read it, so the app avoids third-party scripts and tokens expire after hours.
let token = null;
try { token = localStorage.getItem(TOKEN_KEY); } catch { /* storage blocked: stay signed out after reload */ }

let onUnauthorized = null;

export function setToken(value) {
  token = value;
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* ignore */ }
}

function message(body, fallback) {
  const d = body && body.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
  return fallback;
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  });
  if (!res.ok) {
    let body = null;
    try { body = await res.json(); } catch { /* not JSON */ }
    // A 401 on a normal call means the session ended; the login call handles its own 401.
    if (res.status === 401 && token && path !== "/auth/login") {
      setToken(null);
      onUnauthorized?.();
    }
    const err = new Error(message(body, res.statusText));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

const json = (method, body) => ({ method, body: JSON.stringify(body) });

export const api = {
  base: BASE,
  setUnauthorizedHandler: (fn) => { onUnauthorized = fn; },
  handleUnauthorized: () => { setToken(null); onUnauthorized?.(); },
  hasToken: () => !!token,
  authHeaders: () => (token ? { Authorization: `Bearer ${token}` } : {}),

  health: () => request("/health"),
  login: (email, password) => request("/auth/login", json("POST", { email, password })),
  me: () => request("/auth/me"),
  changePassword: (current_password, new_password) =>
    request("/auth/change-password", json("POST", { current_password, new_password })),
  listUsers: () => request("/users"),
  createUser: (body) => request("/users", json("POST", body)),
  updateUser: (id, body) => request(`/users/${id}`, json("PATCH", body)),

  stats: () => request("/stats"),
  listTickets: ({ status, limit = 50, offset = 0 } = {}) => {
    const q = new URLSearchParams({ limit, offset });
    if (status) q.set("status", status);
    return request(`/tickets?${q}`);
  },
  getTicket: (id) => request(`/tickets/${encodeURIComponent(id)}`),
  getTrace: (id) => request(`/tickets/${encodeURIComponent(id)}/trace`),
  submit: (text) => request("/tickets", json("POST", { text })),
  review: (id, body) => request(`/tickets/${encodeURIComponent(id)}/review`, json("POST", body)),
  streamUrl: (id) => `${BASE}/tickets/${encodeURIComponent(id)}/stream`,
};
