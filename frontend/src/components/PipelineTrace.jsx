import { Check, Loader2, Circle, ShieldAlert, ShieldCheck, UserCheck, AlertTriangle, MinusCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { buildSteps } from "../lib/pipeline.js";
import { clock } from "../lib/format.js";
import { Card, ConfidenceBar, Pill, ReasonChip, CategoryPill, cx } from "./ui.jsx";

const TITLES = { intake: "Intake", triage: "Intent classification and triage", specialist: "Specialist", guardrail: "Safety and policy guardrail", outcome: "Outcome" };

function Marker({ status }) {
  const base = "grid h-6 w-6 shrink-0 place-items-center rounded-full border-2 bg-surface";
  if (status === "done") return <div className={cx(base, "border-ok text-ok")}><Check size={13} strokeWidth={3} /></div>;
  if (status === "running") return <div className={cx(base, "border-accent text-accent")}><Loader2 size={13} className="animate-spin" /></div>;
  if (status === "skipped") return <div className={cx(base, "border-bad text-bad")}><ShieldAlert size={12} /></div>;
  return <div className={cx(base, "border-line text-line")}><Circle size={8} /></div>;
}

function StepBody({ step, events, ticket }) {
  const o = step.event?.output || {};
  if (step.key === "intake") return <div className="font-mono text-xs text-muted">{o.chars} characters received, whitespace normalized</div>;
  if (step.key === "triage") {
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <CategoryPill category={o.category} />
          <Pill>sentiment: {o.sentiment}</Pill>
          <Pill tone={o.urgency === "high" ? "warn" : "neutral"}>urgency: {o.urgency}</Pill>
          {(o.risk_flags || []).map((f) => <ReasonChip key={f} reason={f} />)}
        </div>
        <ConfidenceBar label="Classification confidence" value={o.triage_confidence} threshold={0.75} />
        {o.error && <div className="text-xs text-bad">{o.error}</div>}
      </div>
    );
  }
  if (step.key === "specialist") {
    if (step.status === "skipped") {
      const q = events.find((e) => e.node === "quarantine");
      return (
        <div className="flex items-start gap-2 text-sm text-muted">
          <ShieldAlert size={15} className="mt-0.5 shrink-0 text-bad" />
          {q ? "Prompt injection detected. The specialist was skipped so the attacker's text never reaches an agent that drafts replies."
             : "Category is \"other\", so no specialist was used."}
        </div>
      );
    }
    return (
      <div className="space-y-3">
        <Pill tone="accent" mono>{o.specialist_used}</Pill>
        {o.draft_reply
          ? <blockquote className="rounded-md border-l-2 border-accent bg-sunken px-3 py-2 text-sm leading-relaxed">{o.draft_reply}</blockquote>
          : <div className="text-xs text-bad">{o.error || "No draft was produced."}</div>}
        {o.commits_to_refund_usd != null && <div className="text-xs text-muted">Draft commits to a refund of <span className="font-mono text-ink">${o.commits_to_refund_usd}</span></div>}
        <ConfidenceBar label="Specialist confidence" value={o.specialist_confidence} threshold={0.75} />
      </div>
    );
  }
  if (step.key === "guardrail") {
    const reasons = o.guardrail_reasons || [];
    return reasons.length ? (
      <div className="space-y-2">
        <div className="text-xs text-muted">Deterministic rules fired. No LLM is involved in this decision.</div>
        <div className="flex flex-wrap gap-1.5">{reasons.map((r, i) => <ReasonChip key={r} reason={r} primary={i === 0} />)}</div>
      </div>
    ) : (
      <div className="flex items-center gap-1.5 text-sm text-ok"><ShieldCheck size={15} /> No rule fired. Safe to auto-resolve.</div>
    );
  }
  return null;
}

function Outcome({ step, ticket, done }) {
  if (step.status !== "done") return null;
  const escalated = step.event.node === "escalate";
  return (
    <div className={cx("flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3",
      escalated ? "border-warn/40 bg-warn-tint" : "border-ok/40 bg-ok-tint")}>
      <div className="flex items-center gap-3">
        {escalated ? <UserCheck className="text-warn" size={22} /> : <Check className="text-ok" size={22} />}
        <div>
          <div className="text-sm font-semibold">{escalated ? "Escalated to a human" : "Auto-resolved"}</div>
          <div className="text-xs text-muted">
            {escalated ? "A reviewer will see the full context and the drafted reply." : "The drafted reply was sent without human review."}
          </div>
        </div>
      </div>
      <div className="flex gap-2">
        {escalated && <Link to="/review" className="rounded-md bg-warn px-3 py-1.5 text-sm font-medium text-white hover:brightness-95">Open Review Queue</Link>}
        {ticket && <Link to={`/audit/${ticket}`} className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm hover:bg-sunken">View audit trail</Link>}
      </div>
    </div>
  );
}

export default function PipelineTrace({ ticketId, events, done, error }) {
  const crash = events.find((e) => e.node === "system_error");
  const steps = buildSteps(events, !!done);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">Pipeline trace</h2>
          <Pill mono>{ticketId}</Pill>
        </div>
      </div>

      <ol className="relative space-y-3">
        <div className="absolute bottom-3 left-3 top-3 w-px bg-line" />
        {steps.map((step) => {
          if (step.key === "outcome") {
            return <li key={step.key} className="relative pl-10"><div className="absolute left-0 top-3"><Marker status={step.status} /></div>
              {step.status === "done" ? <Outcome step={step} ticket={ticketId} done={done} />
                : <Card className="px-4 py-3 text-sm text-muted">{TITLES.outcome}</Card>}</li>;
          }
          if (step.key === "intake" && step.status === "done") {
            return (
              <li key={step.key} className="step-in relative pl-10">
                <div className="absolute left-0 top-1.5"><Marker status="done" /></div>
                <div className="flex items-center justify-between px-1 py-1.5 text-sm">
                  <span className="font-medium">Intake <span className="font-normal text-muted">· {step.event.output.chars} characters</span></span>
                  <span className="font-mono text-[11px] text-muted">{clock(step.event.at)}</span>
                </div>
              </li>
            );
          }
          return (
            <li key={step.key} className={cx("relative pl-10", step.status === "done" && "step-in")}>
              <div className="absolute left-0 top-3"><Marker status={step.status} /></div>
              <Card className={cx("px-4 py-3", step.status === "pending" && "opacity-50")}>
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium">
                    {step.key === "specialist" && step.status === "skipped" ? "Specialist skipped" : TITLES[step.key]}
                  </div>
                  <div className="font-mono text-[11px] text-muted">
                    {step.status === "running" ? "running…" : step.event ? clock(step.event.at) : ""}
                  </div>
                </div>
                {(step.status === "done" || step.status === "skipped") && (
                  <div className="mt-2"><StepBody step={step} events={events} /></div>
                )}
              </Card>
            </li>
          );
        })}
      </ol>

      {crash && (
        <div className="mt-3 flex items-start gap-2 rounded-md border border-bad/30 bg-bad-tint px-3 py-2 text-sm text-bad">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <div>The pipeline crashed and the ticket failed closed. It was not auto-resolved and can be reviewed by a human.
            <div className="mt-1 font-mono text-xs">{crash.output?.error}</div></div>
        </div>
      )}
      {error && <div className="mt-3 text-sm text-bad">{error}</div>}
    </div>
  );
}
