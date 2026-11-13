import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Send, Activity } from "lucide-react";
import { api } from "../lib/api.js";
import { usePolling } from "../lib/usePolling.js";
import { useTicketStream } from "../lib/useTicketStream.js";
import { SAMPLES } from "../lib/samples.js";
import { timeAgo, shortId } from "../lib/format.js";
import PipelineTrace from "../components/PipelineTrace.jsx";
import { Button, Card, CategoryPill, Empty, ErrorNote, ReasonChip, StatusBadge, cx } from "../components/ui.jsx";

const MAX = 5000;

export default function LiveConsole() {
  const [params, setParams] = useSearchParams();
  const ticketId = params.get("ticket");
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  const recent = usePolling(() => api.listTickets({ limit: 8 }), 4000);
  const { events, done, error } = useTicketStream(ticketId, recent.reload);

  async function run() {
    if (!text.trim() || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const t = await api.submit(text.trim());
      setParams({ ticket: t.id });
      recent.reload();
    } catch (e) {
      setSubmitError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid gap-6 p-6 xl:grid-cols-[minmax(340px,35%)_1fr]">
      <div className="space-y-4">
        <Card className="p-4">
          <h2 className="font-semibold">Submit a ticket</h2>
          <p className="mb-3 text-xs text-muted">Paste a customer message and watch the pipeline decide.</p>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, MAX))}
            onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run(); }}
            rows={6}
            placeholder="Paste a customer message..."
            className="w-full resize-none rounded-md border border-line bg-bg p-3 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/15"
          />
          <div className="mt-1 text-right font-mono text-[11px] text-muted">{text.length} / {MAX}</div>
          <div className="mt-3 text-[11px] font-medium uppercase tracking-wide text-muted">Sample tickets</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {SAMPLES.map((s) => (
              <button key={s.label} onClick={() => setText(s.text)}
                className="rounded-md border border-line bg-surface px-2 py-1 text-xs hover:bg-sunken">{s.label}</button>
            ))}
          </div>
          {submitError && <div className="mt-3"><ErrorNote>{submitError}</ErrorNote></div>}
          <Button variant="primary" icon={Send} onClick={run} disabled={!text.trim() || submitting} className="mt-4 w-full">
            {submitting ? "Submitting…" : "Run pipeline"}
          </Button>
        </Card>

        <Card>
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <h3 className="text-sm font-semibold">Recent tickets</h3>
            <span className="text-[11px] text-muted">{recent.data ? `${recent.data.total} total` : ""}</span>
          </div>
          {recent.error && <div className="p-3"><ErrorNote>Cannot reach the API: {recent.error}</ErrorNote></div>}
          {recent.data?.items.length === 0 && <Empty icon={Activity} title="No tickets yet" hint="Run a sample ticket to see the pipeline." />}
          <ul>
            {recent.data?.items.map((t) => (
              <li key={t.id}>
                <button onClick={() => setParams({ ticket: t.id })}
                  className={cx("block w-full border-b border-line px-4 py-2.5 text-left last:border-0 hover:bg-sunken",
                    t.id === ticketId && "bg-accent-tint/60")}>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs">#{shortId(t.id)}</span>
                    <StatusBadge status={t.status} reviewAction={t.review_action} />
                  </div>
                  <div className="mt-1 line-clamp-1 text-xs text-muted">{t.text}</div>
                  <div className="mt-1 flex items-center gap-1.5">
                    <CategoryPill category={t.category} />
                    {t.primary_reason && <ReasonChip reason={t.primary_reason} />}
                    <span className="ml-auto text-[11px] text-muted">{timeAgo(t.created_at)}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div>
        {ticketId
          ? <PipelineTrace ticketId={ticketId} events={events} done={done} error={error} />
          : <Card><Empty icon={Activity} title="Nothing running"
              hint="Submit a ticket or pick one from the list. Each step appears here as it finishes." /></Card>}
      </div>
    </div>
  );
}
