// Static results copied from the README. They come from the offline eval runner
// (scripts/run_pipeline.py), not from the live database, so they are labelled as such in the UI.
export const MODEL_RESULTS = {
  heldout: {
    title: "Held-out v2 (50 tickets, 26 should escalate)",
    note:
      "One run per model, written after the guardrail fixes. 26 risky tickets means 26/26 still allows a true miss rate near 11%. " +
      "Both models missed prompt injections phrased as a note to the AI. On v1 (before the fixes) recall was 96% and 88% with 1 and 3 unsafe auto-resolves.",
    rows: [
      { model: "gpt-oss-20b", accuracy: "92%", recall: "100% (26/26)", unsafe: 0, over: "17%" },
      { model: "gpt-oss-120b", accuracy: "96%", recall: "100% (26/26)", unsafe: 0, over: "4%" },
    ],
  },
  heldoutV1: {
    title: "Held-out v1 (50 tickets, 25 should escalate), before the fixes",
    note: "One run per model. Used up for evaluating fixes.",
    rows: [
      { model: "gpt-oss-20b", accuracy: "90%", recall: "96% (24/25)", unsafe: 1, over: "12%" },
      { model: "gpt-oss-120b", accuracy: "94%", recall: "88% (22/25)", unsafe: 3, over: "12%" },
    ],
  },
  dev: {
    title: "Dev set (100 synthetic tickets, 28 should escalate)",
    note: "Regexes were written while looking at this set, so these numbers are optimistic.",
    rows: [
      { model: "Keyword stub (no LLM)", accuracy: "85%", recall: "79% (22/28)", unsafe: 6, over: "4%" },
      { model: "gpt-oss-20b", accuracy: "93%", recall: "100% (28/28)", unsafe: 0, over: "4%" },
      { model: "gpt-oss-120b", accuracy: "94%", recall: "100% (28/28)", unsafe: 0, over: "6%" },
    ],
  },
};
