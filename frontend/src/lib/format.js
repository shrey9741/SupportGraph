export function timeAgo(iso) {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 10) return "just now";
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function clock(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function durationSeconds(a, b) {
  if (!a || !b) return null;
  return (new Date(b).getTime() - new Date(a).getTime()) / 1000;
}

export const pct = (v) => (v == null ? "n/a" : `${Math.round(v * 100)}%`);

export function statusLabel(status, reviewAction) {
  if (reviewAction) return { approve: "Approved", edit: "Edited", reject: "Rejected" }[reviewAction];
  return { processing: "Processing", auto_resolved: "Auto-resolved", escalated: "Escalated", failed: "Failed" }[status] || status;
}

export function shortId(id) {
  return id && id.length > 12 ? id.slice(0, 12) : id;
}
