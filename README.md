cd D:\SupportGraph

A multi-agent customer success automation system. It triages support tickets,
routes them to specialist agents, applies a guardrail, and either auto-resolves
or escalates to a human with full context.

**Stack:** LangGraph, FastAPI, Pydantic, SQLite, React (Vite + Tailwind)

## Status

- [x] Day 1: repo scaffold, escalation policy, schemas, labeled seed dataset (100 tickets)
- [x] Day 2: LangGraph pipeline (intake, triage, 3 specialists, guardrail, resolve, escalate), offline stub model, Groq client, eval runner, 26 unit tests
- [x] First real-model evaluation runs on Groq (gpt-oss-20b and gpt-oss-120b)
- [x] Prompt-injection quarantine step
- [x] Held-out test set drafted (50 tickets, `data/tickets_heldout.jsonl`); labels need owner review before any model run
- [x] Held-out v1 evaluation (run once per model, no tuning afterward)
- [ ] Fix the known gaps, then validate on a fresh held-out v2 set
- [ ] FastAPI backend and SQLite audit log
- [ ] React frontend with live trace
- [ ] Evaluation dashboard

## How it works

```
intake -> triage -> billing | technical | account specialist -> guardrail -> resolve | escalate
                 \-> (category "other") ---------------------> guardrail -/
```

- **Triage** (LLM): category, sentiment, urgency, confidence, and `risk_flags`.
- **Specialists** (LLM): draft a reply with a confidence score.
- **Guardrail** (plain Python, no LLM): escalates if any rule fires. Reasons come
  from the model's `risk_flags` plus a regex safety net for the highest-stakes
  patterns. See `docs/policy.md`.
- **Fail closed:** if an LLM call fails after its retries, the error is recorded
  and the ticket escalates. A failure never auto-resolves.
- **Audit trail:** every node appends an event to `trace` in the shared state.
- Ticket text is wrapped in `<ticket>` tags and treated as untrusted input.
- **Quarantine:** tickets containing a prompt injection skip the specialists
  entirely, so attacker-written instructions never reach an agent that drafts
  refunds. The audit trace records why.

## Layout

```
backend/app/     schemas, state, llm client, prompts, nodes, graph, guardrail, stub model
backend/tests/   unit tests (guardrail rules, routing, fail-closed, retries)
data/            labeled tickets, builder script, saved eval results
docs/policy.md   single source of truth for labels and guardrail rules
scripts/         dataset validation and the eval runner
frontend/        React app (coming)
```

## Setup

```bash
pip install -r backend/requirements.txt
cp .env.example .env          # then edit .env
python scripts/validate_dataset.py
cd backend && python -m pytest -q
```

`.env` settings: `LLM_PROVIDER` (`stub` or `groq`), `LLM_MODEL`, `GROQ_API_KEY`,
`CONFIDENCE_THRESHOLD`, `REFUND_AUTO_LIMIT_USD`, `MAX_LLM_ATTEMPTS`.

## Run the evaluation

```bash
python scripts/run_pipeline.py                         # uses LLM_PROVIDER from .env
python scripts/run_pipeline.py --provider groq --delay 2.5   # real model, gentle on rate limits
python scripts/run_pipeline.py --provider stub --verbose     # offline baseline
```

Results are saved per ticket as they finish, so a rate limit or crash never
loses progress; re-running skips finished tickets (`--fresh` starts over).

## Held-out evaluation

`data/tickets_heldout.jsonl` is for final numbers only. It is written in a
different style from the dev set (typos, Hinglish and Spanish, multi-issue
messages, paraphrased threats and injections that the regexes do not literally
match, and benign look-alikes). Rules: review every label first, run each model
once, and never tune on it afterward.

```bash
python data/build_heldout.py        # prints every label for review
python scripts/run_pipeline.py --provider groq --delay 2.5 --dataset data/tickets_heldout.jsonl
```

Held-out results are saved in separate files and never mix with the dev set.

### Held-out v1 results (50 tickets, 25 should escalate, one run per model)

| Metric | gpt-oss-20b | gpt-oss-120b |
|---|---|---|
| Category accuracy | 90% | 94% |
| Escalation recall | 96% (24/25) | 88% (22/25) |
| Unsafe auto-resolves | 1 | 3 |
| Over-escalation | 12% (3/25) | 12% (3/25) |
| Primary reason match (strict) | 88% | 76% |
| Reason found anywhere | 88% | 84% |

Recall dropped from 100% on the dev set to 88-96% here, which is why the held-out
set exists. With 25 risky tickets the true recall could plausibly be anywhere from
about 70% to 96%, and the 2-ticket gap between the models is within run-to-run
noise, so neither model is shown to be better.

Gaps seen in both models (these are the actionable ones; one-off differences are
mostly noise):
- Pricing negotiation (volume discount, seats) is not recognised as `sales_enterprise`.
- Some risky tickets are escalated for the wrong reason (for example a disputed
  invoice escalated only as `low_confidence`), which is safe but fragile.
- A Hinglish "payment failed, money deducted" ticket is over-escalated as `angry_customer`.
- Questions that depend on company knowledge (refund policy, import size limits)
  escalate on `low_confidence` because the specialists have no knowledge source.
  This caps the auto-resolve rate more than model quality does.

This set is now burned for evaluating fixes. Fixes get validated on a fresh set.

## Results (100 synthetic dev tickets)

Repeated runs of the same model on the same tickets differ by a few tickets
(Groq output is not fully deterministic even at temperature 0), so treat
differences of 1-3 tickets as noise.

| Metric | Keyword stub (no LLM) | gpt-oss-20b | gpt-oss-120b |
|---|---|---|---|
| Category accuracy | 85% | 93% | 94% |
| Escalation recall | 79% (22/28) | 100% (28/28) | 100% (28/28) |
| Unsafe auto-resolves | 6 | 0 | 0 |
| Over-escalation | 4% (3/72) | 4% (3/72) | 6% (4/72) |
| Primary reason match (strict) | 68% | 86% | 82% |
| Auto-resolve rate (ceiling 72%) | 75% | 69% | 68% |

"Unsafe auto-resolve" means a ticket that should have gone to a human but was
closed automatically. It is the metric that matters most. The stub's 75%
auto-resolve rate is above the 72% ceiling because some of what it closed
should have escalated.

Takeaways: the models beat the keyword baseline on every safety metric, and the
larger 120b model showed no measurable gain over the 20b on this set (every
difference is 1-2 tickets, which is noise), so the cheaper 20b is the default.
These runs were made before the prompt-injection quarantine step was added.
Most category "errors" are ambiguous labels (for example, API keys as account
vs technical), not model failures.

**Limits:** 28 risky tickets is small (0 misses could still hide a true miss rate
near 10%), the data is synthetic and self-labeled, and the guardrail regexes were
written while looking at this set. A held-out test set is the next step.

## Notes

The seed dataset is hand-labeled and synthetic. It is a starting point for
evaluation, not a claim about real-world traffic. The guardrail regexes were
written while looking at this dataset, so numbers on it can be optimistic; a
held-out set is needed before making strong claims.
