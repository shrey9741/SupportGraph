import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronDown, ChevronRight, Copy, Check, ScrollText, Search, ArrowLeft, UserCheck, Shield, Brain, FileInput, CircleCheck, ShieldAlert, AlertTriangle, Wrench, CreditCard, User } from "lucide-react";
import { api } from "../lib/api.js";
import { usePolling } from "../lib/usePolling.js";
import { clock, durationSeconds, shortId, timeAgo } from "../lib/format.js";
import JsonView from "../components/JsonView.jsx";
import { Button, Card, CategoryPill, ConfidenceBar, Empty, ErrorNote, Pill, ReasonChip, StatusBadge, cx } from "../components/ui.jsx";

const FILTERS = [["", "All"], ["auto_resolved", "Auto-resolved"], ["escalated", "Escalated"], ["failed", "Failed"]];

export default function Audit() {
  const { id } = useParams();
  return id ? <AuditDetail id={id} /> : <AuditList />;
}

function AuditList() {
  const nav = useNavigate();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const list = usePolling(() => api.listTickets({ status: status || undefined, limit: 200 }), 6000, [status]);
  const rows = useMemo(() => {
    const s = q.trim().toLowerCase();
    const items = list.data?.items || [];
    return s ? items.filter((t) => t.id.toLowerCase().includes(s) || t.text.toLowerCase().includes(s)) : items;
  }, [list.data, q]);

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <div>
        <h1 className="text-lg font-semibold">Ticket Audit Trail</h1>
        <p className="text-xs text-muted">Every decision the system made, per ticket. Open one to see each step.</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-60 flex-1">
          <Search size={14} className="absolute left-2.5 top-2.5 text-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by ticket ID or text"
            className="w-full rounded-md border border-line bg-surface py-1.5 pl-8 pr-3 text-sm outline-none focus:border-accent" />
        </div>
        <div className="flex rounded-md border border-line bg-surface p-0.5">
          {FILTERS.map(([k, label]) => (
            <button key={k} onClick={() => setStatus(k)}
              className={cx("rounded px-3 py-1 text-sm", status === k ? "bg-accent-tint font-medium text-accent" : "text-muted hover:text-ink")}>{label}</button>
          ))}
        </div>
      </div>
      {list.error && <ErrorNote>Cannot reach the API: {list.error}</ErrorNote>}
      <Card>
        {rows.length === 0 && <Empty icon={ScrollText} title="No tickets found" />}
        {rows.map((t) => (
          <button key={t.id} onClick={() => nav(`/audit/${t.id}`)}
            className="flex w-full items-center gap-4 border-b border-line px-4 py-3 text-left last:border-0 hover:bg-sunken">
            <span className="w-28 shrink-0 font-mono text-xs">#{shortId(t.id)}</span>
            <span className="line-clamp-1 flex-1 text-sm text-muted">{t.text}</span>
            <CategoryPill category={t.category} />
            {t.primary_reason && <ReasonChip reason={t.primary_reason} />}
            <StatusBadge status={t.status} reviewAction={t.review_action} />
            <span className="w-16 shrink-0 text-right text-[11px] text-muted">{timeAgo(t.created_at)}</span>
          </button>
        ))}
      </Card>
    </div>
  );
}

const NODE_ICON = {
  intake: FileInput, triage: Brain, quarantine: ShieldAlert, guardrail: Shield, resolve: CircleCheck,
  escalate: UserCheck, human_review: UserCheck, system_error: AlertTriangle,
  billing_specialist: CreditCard, technical_specialist: Wrench, account_specialist: User,
};


function offset(ev, start) {
  const ms = new Date(ev.at) - new Date(start);
  if (!Number.isFinite(ms)) return "";
  if (ms < 1000) return `+${Math.max(0, Math.round(ms))}ms`;
  if (ms < 60000) return `+${(ms / 1000).toFixed(1)}s`;
  return `+${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

function summary(ev) {
  const o = ev.output || {};
  switch (ev.node) {
    case "intake": return `${o.chars} characters received`;
    case "triage": return `${o.category}, ${o.sentiment}, urgency ${o.urgency}, confidence ${Math.round((o.triage_confidence ?? 0) * 100)}%`;
    case "quarantine": return "Prompt injection detected. Specialist skipped.";
    case "guardrail": return o.guardrail_reasons?.length ? `Rules fired: ${o.guardrail_reasons.join(", ")}` : "No rule fired";
    case "resolve": return "Reply sent automatically";
    case "escalate": return `Escalated. Primary reason: ${o.primary_reason ?? "none"}`;
    case "human_review": return `${o.reviewer} chose "${o.action}"${o.note ? `: ${o.note}` : ""}`;
    case "system_error": return o.error || "Pipeline crashed";
    default:
      if (ev.node.endsWith("_specialist")) return o.draft_reply ? `Drafted a reply, confidence ${Math.round((o.specialist_confidence ?? 0) * 100)}%` : (o.error || "No draft produced");
      return "";
  }
}

function AuditDetail({ id }) {
  const trace = usePolling(() => api.getTrace(id), 0, [id]);
  const ticket = usePolling(() => api.getTicket(id), 0, [id]);
  const [open, setOpen] = useState({});
  const [copied, setCopied] = useState(false);
  const t = ticket.data;
  const events = trace.data?.events || [];
  useEffect(() => { setOpen({}); }, [id]);

  if (trace.error || ticket.error) return <div className="p-6"><ErrorNote>{trace.error || ticket.error}</ErrorNote></div>;
  if (!t) return <div className="p-6 text-sm text-muted">Loading…</div>;

  const secs = durationSeconds(t.created_at, t.completed_at);
  const start = events[0]?.at;
  const reviewEv = events.find((e) => e.node === "human_review");
  const waitSecs = reviewEv && t.completed_at ? durationSeconds(t.completed_at, reviewEv.at) : null;
  const fmtWait = (x) => (x < 90 ? `${Math.round(x)}s` : x < 5400 ? `${Math.round(x / 60)}m` : `${(x / 3600).toFixed(1)}h`);
  async function copy() {
    try { await navigator.clipboard.writeText(JSON.stringify(events, null, 2)); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <Link to="/audit" className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink"><ArrowLeft size={13} /> All tickets</Link>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="font-mono text-lg font-semibold">#{t.id}</h1>
          <StatusBadge status={t.status} reviewAction={t.review?.action} />
        </div>
        <div className="flex items-center gap-4 text-xs text-muted">
          <span>Created <span className="font-mono text-ink">{clock(t.created_at)}</span></span>
          {secs != null && <span>Pipeline <span className="font-mono text-ink">{secs.toFixed(1)}s</span></span>}
          {waitSecs != null && <span>Waited for review <span className="font-mono text-ink">{fmtWait(waitSecs)}</span></span>}
          <span><span className="font-mono text-ink">{events.length}</span> nodes executed</span>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <div>
          <div className="relative space-y-3">
            <div className="absolute bottom-4 left-[15px] top-4 w-px bg-line" />
            {events.map((ev) => {
              const Icon = NODE_ICON[ev.node] || Shield;
              const isOpen = open[ev.seq];
              const hr = ev.node === "human_review";
              const violation = ev.node === "guardrail" && ev.output?.guardrail_reasons?.length > 0;
              return (
                <div key={ev.seq} className="relative pl-11">
                  <div className={cx("absolute left-0 top-2.5 grid h-8 w-8 place-items-center rounded-full border bg-surface",
                    hr ? "border-accent text-accent" : ev.node === "system_error" ? "border-bad text-bad" : "border-line text-muted")}>
                    <Icon size={15} />
                  </div>
                  <Card className={cx(hr && "!border-accent/40 !bg-accent-tint/40", violation && "!border-bad/40 !bg-bad-tint/50")}>
                    <button onClick={() => setOpen((o) => ({ ...o, [ev.seq]: !o[ev.seq] }))}
                      className="flex w-full items-start gap-2 px-4 py-3 text-left">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-2">
                            <span className="font-mono text-sm font-medium">{ev.node}</span>
                            {violation && <Pill tone="bad">Rules fired</Pill>}
                          </span>
                          <span className="font-mono text-[11px] text-muted">{clock(ev.at)} <span className="ml-1 text-accent">{start && ev !== events[0] ? offset(ev, start) : "+0ms"}</span></span>
                        </div>
                        <div className="mt-0.5 text-xs text-muted">{summary(ev)}</div>
                        {ev.node.endsWith("_specialist") && ev.output?.specialist_confidence != null && (
                          <div className="mt-2 max-w-xs"><ConfidenceBar label="Specialist confidence" value={ev.output.specialist_confidence} threshold={0.75} /></div>
                        )}
                        {hr && (
                          <div className="mt-2 flex items-center gap-2 text-xs">
                            <span className="grid h-6 w-6 place-items-center rounded-full bg-accent text-[10px] font-semibold text-white">
                              {(ev.output?.reviewer || "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                            </span>
                            <span>Reviewed by <b>{ev.output?.reviewer}</b>, action <b>{ev.output?.action}</b></span>
                          </div>
                        )}
                      </div>
                      {isOpen ? <ChevronDown size={15} className="mt-0.5 text-muted" /> : <ChevronRight size={15} className="mt-0.5 text-muted" />}
                    </button>
                    {isOpen && <div className="border-t border-line p-3"><JsonView value={ev.output} /></div>}
                  </Card>
                </div>
              );
            })}
            {events.length === 0 && <Card><Empty icon={ScrollText} title="No events recorded" /></Card>}
          </div>
        </div>

        <div className="space-y-4">
          <Card className="space-y-3 p-4">
            <div className="text-sm font-semibold">Summary</div>
            <Row label="Category"><CategoryPill category={t.category} /></Row>
            <Row label="Primary reason">{t.primary_reason ? <ReasonChip reason={t.primary_reason} primary /> : <span className="text-xs text-muted">none</span>}</Row>
            {t.reasons.length > 1 && (
              <Row label="All reasons"><div className="flex flex-wrap justify-end gap-1">{t.reasons.map((r) => <ReasonChip key={r} reason={r} />)}</div></Row>
            )}
            <div>
              <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted">Customer message</div>
              <p className="text-sm leading-relaxed">{t.text}</p>
            </div>
            <div>
              <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted">Final reply</div>
              <p className="text-sm leading-relaxed">{t.review?.final_reply || t.final_reply || <span className="text-muted">No reply was sent.</span>}</p>
            </div>
          </Card>
          <Button icon={copied ? Check : Copy} onClick={copy} className="w-full">{copied ? "Copied" : "Copy trace as JSON"}</Button>
        </div>
      </div>
    </div>
  );
}

function Row({ label, children }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs text-muted">{label}</span>
      {children}
    </div>
  );
}
