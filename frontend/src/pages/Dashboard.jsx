import { BarChart3, Clock, ListChecks, OctagonAlert, TicketCheck, UserCheck } from "lucide-react";
import { api } from "../lib/api.js";
import { usePolling } from "../lib/usePolling.js";
import { pct } from "../lib/format.js";
import { MODEL_RESULTS } from "../lib/modelResults.js";
import { Card, ErrorNote, Empty, cx } from "../components/ui.jsx";

function Kpi({ icon: Icon, label, value, hint }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between text-xs text-muted">{label}<Icon size={15} /></div>
      <div className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-[11px] text-muted">{hint}</div>
    </Card>
  );
}

function Panel({ title, sub, children }) {
  return (
    <Card className="p-4">
      <div className="text-sm font-semibold">{title}</div>
      {sub && <div className="mb-4 text-xs text-muted">{sub}</div>}
      {children}
    </Card>
  );
}

export default function Dashboard() {
  const { data: s, error } = usePolling(api.stats, 8000);
  const results = MODEL_RESULTS.heldout;

  if (error) return <div className="p-6"><ErrorNote>Cannot reach the API: {error}</ErrorNote></div>;
  if (!s) return <div className="p-6 text-sm text-muted">Loading…</div>;

  const reviewTotal = s.reviews.approve + s.reviews.edit + s.reviews.reject;
  const maxReason = Math.max(1, ...s.top_escalation_reasons.map((r) => r.count));

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <div>
        <h1 className="text-lg font-semibold">Operations dashboard</h1>
        <p className="text-xs text-muted">Live numbers from this instance's database, plus offline evaluation results.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Kpi icon={TicketCheck} label="Total tickets" value={s.total} hint={s.processing ? `${s.processing} processing` : "all processed"} />
        <Kpi icon={ListChecks} label="Auto-resolve rate" value={pct(s.auto_resolve_rate)} hint={`${s.auto_resolved} auto-resolved`} />
        <Kpi icon={UserCheck} label="Escalated" value={s.escalated} hint="sent to a human" />
        <Kpi icon={OctagonAlert} label="Failed" value={s.failed} hint="failed closed, never auto-resolved" />
        <Kpi icon={Clock} label="Avg processing time" value={s.avg_processing_seconds != null ? `${s.avg_processing_seconds.toFixed(1)}s` : "n/a"} hint="submit to outcome" />
      </div>

      {s.total === 0 && (
        <Card><Empty icon={BarChart3} title="No tickets yet" hint="Run some tickets in the Live Console, or use scripts/seed_demo.py to load sample tickets." /></Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Outcomes by category" sub="How each category ended up">
          <div className="mb-3 flex gap-3 text-[11px] text-muted">
            <Legend color="bg-ok" label="Auto-resolved" /><Legend color="bg-warn" label="Escalated" /><Legend color="bg-bad" label="Failed" />
          </div>
          <div className="space-y-3">
            {s.by_category.map((c) => {
              const failed = c.total - c.auto_resolved - c.escalated;
              return (
                <div key={c.category}>
                  <div className="mb-1 flex justify-between text-xs"><span className="font-medium capitalize">{c.category}</span><span className="font-mono text-muted">{c.total} {c.total === 1 ? "ticket" : "tickets"}</span></div>
                  <div className="flex h-2.5 overflow-hidden rounded-full bg-sunken">
                    <div className="bg-ok" style={{ width: `${(c.auto_resolved / c.total) * 100}%` }} />
                    <div className="bg-warn" style={{ width: `${(c.escalated / c.total) * 100}%` }} />
                    <div className="bg-bad" style={{ width: `${(failed / c.total) * 100}%` }} />
                  </div>
                </div>
              );
            })}
            {s.by_category.length === 0 && <div className="text-xs text-muted">No completed tickets yet.</div>}
          </div>
        </Panel>

        <Panel title="Top escalation reasons" sub="Primary reason on escalated tickets">
          <div className="space-y-2.5">
            {s.top_escalation_reasons.slice(0, 7).map((r) => (
              <div key={r.reason}>
                <div className="mb-1 flex justify-between text-xs"><span className="font-mono">{r.reason}</span><span className="font-mono text-muted">{r.count}</span></div>
                <div className="h-2 overflow-hidden rounded-full bg-sunken">
                  <div className={cx("h-full", r.reason === "prompt_injection" ? "bg-bad" : "bg-accent")} style={{ width: `${(r.count / maxReason) * 100}%` }} />
                </div>
              </div>
            ))}
            {s.top_escalation_reasons.length === 0 && <div className="text-xs text-muted">No escalations yet.</div>}
          </div>
        </Panel>

        <Panel title="Human review decisions" sub="What reviewers did with escalated tickets">
          {reviewTotal === 0 ? <div className="text-xs text-muted">No reviews yet. Approve, edit or reject a ticket in the Review Queue.</div> : (
            <div className="flex items-center gap-6">
              <Donut parts={[["approve", s.reviews.approve, "#2f9e6b"], ["edit", s.reviews.edit, "#7a2e65"], ["reject", s.reviews.reject, "#d14343"]]} total={reviewTotal} />
              <ul className="space-y-1.5 text-sm">
                {[["Approve", s.reviews.approve, "bg-ok"], ["Edit", s.reviews.edit, "bg-accent"], ["Reject", s.reviews.reject, "bg-bad"]].map(([l, n, c]) => (
                  <li key={l} className="flex items-center gap-2"><span className={cx("h-2.5 w-2.5 rounded-sm", c)} />{l}<span className="ml-2 font-mono text-muted">{n}</span></li>
                ))}
              </ul>
            </div>
          )}
        </Panel>

        <Panel title="Model comparison" sub="Offline evaluation, not live traffic">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-muted"><tr>
                <th className="pb-2 font-medium">Model</th><th className="pb-2 font-medium">Category acc.</th>
                <th className="pb-2 font-medium">Escalation recall</th><th className="pb-2 font-medium">Unsafe auto-resolves</th><th className="pb-2 font-medium">Over-esc.</th>
              </tr></thead>
              <tbody>
                {results.rows.map((r) => (
                  <tr key={r.model} className="border-t border-line">
                    <td className="py-2 font-mono">{r.model}</td><td>{r.accuracy}</td><td>{r.recall}</td>
                    <td><span className={cx("rounded px-1.5 py-0.5 font-mono font-semibold", r.unsafe === 0 ? "bg-ok-tint text-ok" : "bg-warn-tint text-[#9a6206]")}>{r.unsafe}</span></td>
                    <td>{r.over}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-muted"><b>{results.title}.</b> {results.note}</p>
        </Panel>
      </div>
    </div>
  );
}

function Legend({ color, label }) {
  return <span className="flex items-center gap-1.5"><span className={cx("h-2 w-2 rounded-sm", color)} />{label}</span>;
}

function Donut({ parts, total }) {
  const r = 38, c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <svg width="120" height="120" viewBox="0 0 100 100" className="shrink-0 -rotate-90">
      <circle cx="50" cy="50" r={r} fill="none" stroke="#f4f0ea" strokeWidth="14" />
      {parts.map(([k, n, color]) => {
        const len = (n / total) * c;
        const el = <circle key={k} cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="14"
          strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-offset} />;
        offset += len;
        return el;
      })}
    </svg>
  );
}
