const BASE = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* keep statusText */ }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  base: BASE,
  health: () => request("/health"),
  stats: () => request("/stats"),
  listTickets: ({ status, limit = 50, offset = 0 } = {}) => {
    const q = new URLSearchParams({ limit, offset });
    if (status) q.set("status", status);
    return request(`/tickets?${q}`);
  },
  getTicket: (id) => request(`/tickets/${encodeURIComponent(id)}`),
  getTrace: (id) => request(`/tickets/${encodeURIComponent(id)}/trace`),
  submit: (text) => request("/tickets", { method: "POST", body: JSON.stringify({ text }) }),
  review: (id, body) =>
    request(`/tickets/${encodeURIComponent(id)}/review`, { method: "POST", body: JSON.stringify(body) }),
  streamUrl: (id) => `${BASE}/tickets/${encodeURIComponent(id)}/stream`,
};
