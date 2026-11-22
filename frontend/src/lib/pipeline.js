/** Turns raw audit events into the five pipeline steps the console shows. */
export const STEPS = ["intake", "triage", "specialist", "guardrail", "outcome"];

export function buildSteps(events, finished) {
  const find = (pred) => events.find(pred);
  const byStep = {
    intake: find((e) => e.node === "intake"),
    triage: find((e) => e.node === "triage"),
    specialist: find((e) => e.node.endsWith("_specialist") || e.node === "quarantine"),
    guardrail: find((e) => e.node === "guardrail"),
    outcome: find((e) => e.node === "resolve" || e.node === "escalate"),
  };
  const crash = find((e) => e.node === "system_error");
  // Category "other" legitimately skips specialists: treat as skipped once the guardrail has run.
  const specialistSkipped = !byStep.specialist && byStep.guardrail;

  let runningAssigned = false;
  return STEPS.map((key) => {
    const ev = byStep[key];
    if (ev) return { key, status: ev.node === "quarantine" ? "skipped" : "done", event: ev };
    if (key === "specialist" && specialistSkipped) return { key, status: "skipped", event: null };
    if (finished || crash) return { key, status: "pending", event: null };
    if (!runningAssigned) { runningAssigned = true; return { key, status: "running", event: null }; }
    return { key, status: "pending", event: null };
  });
}
