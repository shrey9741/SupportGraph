import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Inbox, LayoutDashboard, ScrollText, Terminal, Network } from "lucide-react";
import { api } from "../lib/api.js";
import { usePolling } from "../lib/usePolling.js";
import { cx } from "./ui.jsx";

const NAV = [
  { to: "/", label: "Live Console", icon: Terminal, end: true },
  { to: "/review", label: "Review Queue", icon: Inbox, badge: true },
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/audit", label: "Ticket Audit Trail", icon: ScrollText },
];

const TITLES = { "/": "Live Console", "/review": "Review Queue", "/dashboard": "Dashboard", "/audit": "Audit Trail" };

function HealthPill() {
  const { data, error } = usePolling(api.health, 10000);
  const ok = data && !error;
  return (
    <div className="flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-xs">
      <span className={cx("h-2 w-2 rounded-full", ok ? "bg-ok" : "bg-bad")} />
      <span className="font-mono text-muted">
        {ok ? `Connected · ${data.provider} / ${data.model}` : "API unreachable"}
      </span>
    </div>
  );
}

export default function Layout() {
  const { pathname } = useLocation();
  const base = "/" + (pathname.split("/")[1] || "");
  const { data: queue } = usePolling(() => api.listTickets({ limit: 200 }), 8000);
  const waiting = queue
    ? queue.items.filter((t) => (t.status === "escalated" || t.status === "failed") && !t.review_action).length
    : 0;

  return (
    <div className="flex h-full">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-surface md:flex">
        <div className="flex items-center gap-2.5 px-4 py-4">
          <div className="grid h-8 w-8 place-items-center rounded-md bg-accent text-white"><Network size={17} /></div>
          <div>
            <div className="text-sm font-semibold leading-4">SupportGraph</div>
          </div>
        </div>
        <nav className="flex flex-col gap-0.5 px-2 pt-2">
          {NAV.map(({ to, label, icon: Icon, end, badge }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => cx(
                "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm",
                isActive ? "bg-accent-tint font-medium text-accent" : "text-muted hover:bg-sunken hover:text-ink")}>
              <Icon size={16} />
              <span className="flex-1">{label}</span>
              {badge && waiting > 0 && (
                <span className="rounded-full bg-accent px-1.5 text-[11px] font-medium text-white">{waiting}</span>
              )}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface px-6">
          <div className="text-sm font-medium">{TITLES[base] || ""}</div>
          <HealthPill />
        </header>
        <main className="min-h-0 flex-1 overflow-auto"><Outlet /></main>
      </div>
    </div>
  );
}
