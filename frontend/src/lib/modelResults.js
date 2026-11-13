// Static results copied from the README. They come from the offline eval runner
// (scripts/run_pipeline.py), not from the live database, so they are labelled as such in the UI.
export const MODEL_RESULTS = {
  heldout: {
    title: "Held-out set (50 tickets, 25 should escalate)",
    note: "One run per model, no tuning afterward. With 25 risky tickets, a 2-ticket gap between models is within run-to-run noise.",
    rows: [
      { model: "gpt-oss-20b", accuracy: "90%", recall: "96% (24/25)", unsafe: 1, over: "12%" },
      { model: "gpt-oss-120b", accuracy: "94%", recall: "88% (22/25)", unsafe: 3, over: "12%" },
    ],
  },
  dev: {
    title: "Dev set (100 synthetic tickets, 28 should escalate)",
    note: "Regexes were written while looking at this set, so these numbers are optimistic. Run before the quarantine step existed.",
    rows: [
      { model: "Keyword stub (no LLM)", accuracy: "85%", recall: "79% (22/28)", unsafe: 6, over: "4%" },
      { model: "gpt-oss-20b", accuracy: "93%", recall: "100% (28/28)", unsafe: 0, over: "4%" },
      { model: "gpt-oss-120b", accuracy: "94%", recall: "100% (28/28)", unsafe: 0, over: "6%" },
    ],
  },
};
