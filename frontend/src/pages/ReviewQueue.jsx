import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Ban, CheckCheck, Pencil, ThumbsUp, Inbox, ScrollText } from "lucide-react";
import { api } from "../lib/api.js";
import { usePolling } from "../lib/usePolling.js";
import { timeAgo, shortId } from "../lib/format.js";
import { Button, Card, CategoryPill, ConfidenceBar, Empty, ErrorNote, Pill, ReasonChip, StatusBadge, cx } from "../components/ui.jsx";

const TABS = [
  { key: "escalated", label: "Escalated" },
  { key: "failed", label: "Failed" },
  { key: "reviewed", label: "Reviewed" },
];

function bucket(t) {
  if (t.review_action) return "reviewed";
  if (t.status === "escalated") return "escalated";
  if (t.status === "failed") return "failed";
  return null;
}

export default function ReviewQueue() {
  const list = usePolling(() => api.listTickets({ limit: 200 }), 6000);
  const [tab, setTab] = useState("escalated");
  const [selected, setSelected] = useState(null);

  const groups = useMemo(() => {
    const g = { escalated: [], failed: [], reviewed: [] };
    for (const t of list.data?.items || []) { const b = bucket(t); if (b) g[b].push(t); }
    // Oldest first: the ticket that has waited longest is first in line.
    g.escalated.reverse(); g.failed.reverse();
    return g;
  }, [list.data]);

  const rows = groups[tab];
  useEffect(() => {
    if (!rows.some((r) => r.id === selected)) setSelected(rows[0]?.id ?? null);
  }, [rows, selected]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold">Review Queue</h1>
          <p className="text-xs text-muted">Escalated tickets waiting for a human. Oldest first.</p>
        </div>
        <div className="flex rounded-md border border-line bg-surface p-0.5">
          {TABS.map((t) => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={cx("rounded px-3 py-1 text-sm", tab === t.key ? "bg-accent-tint font-medium text-accent" : "text-muted hover:text-ink")}>
              {t.label} <span className="font-mono text-xs">{groups[t.key].length}</span>
            </button>
          ))}
        </div>
      </div>

      {list.error && <div className="p-6"><ErrorNote>Cannot reach the API: {list.error}</ErrorNote></div>}

      <div className="grid min-h-0 flex-1 lg:grid-cols-[380px_1fr]">
        <div className="min-h-0 overflow-auto border-r border-line bg-surface">
          {rows.length === 0 && (
            <Empty icon={Inbox} title={tab === "reviewed" ? "Nothing reviewed yet" : "Queue is clear"}
              hint={tab === "escalated" ? "Escalated tickets show up here when the guardrail fires." : undefined} />
          )}
          {rows.map((t) => (
            <button key={t.id} onClick={() => setSelected(t.id)}
              className={cx("block w-full border-b border-line px-4 py-3 text-left hover:bg-sunken",
                t.id === selected && "bg-accent-tint/60 shadow-[inset_3px_0_0_var(--color-accent)]")}>
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs">#{shortId(t.id)}</span>
                <span className="text-[11px] text-muted">{timeAgo(t.created_at)}</span>
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <CategoryPill category={t.category} />
                {t.primary_reason && <ReasonChip reason={t.primary_reason} primary />}
                {t.urgency === "high" && <Pill tone="warn">high urgency</Pill>}
                {t.review_action && <StatusBadge status={t.status} reviewAction={t.review_action} />}
              </div>
              <div className="mt-1.5 line-clamp-2 text-sm text-muted">{t.text}</div>
            </button>
          ))}
        </div>

        <div className="min-h-0 overflow-auto">
          {selected
            ? <ReviewDetail key={selected} id={selected} onDone={list.reload} />
            : <Empty icon={Inbox} title="Select a ticket" />}
        </div>
      </div>
    </div>
  );
}

function ReviewDetail({ id, onDone }) {
  const detail = usePolling(() => api.getTicket(id), 0, [id]);
  const t = detail.data;
  const [reply, setReply] = useState("");
  const [reviewer, setReviewer] = useState(() => { try { return localStorage.getItem("sg_reviewer") || ""; } catch { return ""; } });
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => { if (t) setReply(t.draft_reply || ""); }, [t?.id, t?.draft_reply]);

  if (detail.error) return <div className="p-6"><ErrorNote>{detail.error}</ErrorNote></div>;
  if (!t) return <div className="p-6 text-sm text-muted">Loading…</div>;

  const packet = t.escalation_packet || {};
  const hasDraft = !!t.draft_reply;
  const edited = hasDraft ? reply.trim() !== t.draft_reply.trim() : reply.trim().length > 0;
  const canReview = !t.review && (t.status === "escalated" || t.status === "failed");

  async function act(action) {
    if (!reviewer.trim()) { setErr("Enter your name so the decision is attributed in the audit log."); return; }
    setBusy(true); setErr(null);
    try {
      try { localStorage.setItem("sg_reviewer", reviewer.trim()); } catch { /* ignore */ }
      await api.review(t.id, {
        action, reviewer: reviewer.trim(), note: note.trim() || null,
        edited_reply: action === "edit" ? reply : null,
      });
      await detail.reload();
      onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-6">
      {t.review && (
        <div className="flex items-center gap-2 rounded-md border border-ok/30 bg-ok-tint px-3 py-2 text-sm text-ok">
          <CheckCheck size={15} />
          {{ approve: "Approved", edit: "Edited and sent", reject: "Rejected" }[t.review.action]} by{" "}
          <b>{t.review.reviewer}</b> {timeAgo(t.review.at)}
          {t.review.note && <span className="text-muted"> · {t.review.note}</span>}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm">#{t.id}</span>
          <StatusBadge status={t.status} />
        </div>
        <Link to={`/audit/${t.id}`} className="flex items-center gap-1 text-xs text-accent hover:underline">
          <ScrollText size={13} /> Full audit trail
        </Link>
      </div>

      <Card className="p-4">
        <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted">Customer message</div>
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{t.text}</p>
      </Card>

      <Card className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-1.5">
          <CategoryPill category={t.category} />
          {t.sentiment && <Pill>sentiment: {t.sentiment}</Pill>}
          {t.urgency && <Pill tone={t.urgency === "high" ? "warn" : "neutral"}>urgency: {t.urgency}</Pill>}
        </div>
        <div>
          <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted">Why it was escalated</div>
          <div className="flex flex-wrap gap-1.5">
            {t.reasons.map((r, i) => <ReasonChip key={r} reason={r} primary={i === 0} />)}
            {t.reasons.length === 0 && <span className="text-xs text-muted">No guardrail reason recorded.</span>}
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <ConfidenceBar label="Triage confidence" value={packet.triage_confidence} threshold={0.75} />
          <ConfidenceBar label="Specialist confidence" value={packet.specialist_confidence} threshold={0.75} />
        </div>
        {t.error && <ErrorNote>{t.error}</ErrorNote>}
      </Card>

      <Card className="p-4">
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[11px] font-medium uppercase tracking-wide text-muted">Drafted reply</div>
        </div>
        {!hasDraft && (
          <p className="mb-2 text-xs text-muted">
            No draft was generated for this ticket (for example a quarantined prompt injection). You can write a reply and send it as an edit, or reject.
          </p>
        )}
        <textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={7} disabled={!canReview}
          className="w-full resize-y rounded-md border border-line bg-bg p-3 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:opacity-70" />
      </Card>

      {canReview && (
        <Card className="space-y-3 p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-xs text-muted">Reviewer name
              <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Your name"
                className="mt-1 w-full rounded-md border border-line bg-bg px-2.5 py-1.5 text-sm text-ink outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">Note (optional)
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Resolution note"
                className="mt-1 w-full rounded-md border border-line bg-bg px-2.5 py-1.5 text-sm text-ink outline-none focus:border-accent" />
            </label>
          </div>
          {err && <ErrorNote>{err}</ErrorNote>}
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="danger" icon={Ban} disabled={busy} onClick={() => act("reject")}>Reject</Button>
            <Button icon={Pencil} disabled={busy || !edited} onClick={() => act("edit")}>Edit and send</Button>
            <Button variant="ok" icon={ThumbsUp} disabled={busy || !hasDraft || edited} onClick={() => act("approve")}>Approve draft</Button>
          </div>
        </Card>
      )}
    </div>
  );
}
