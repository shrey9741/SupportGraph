<h1 align="center">🕸️ SupportGraph</h1>

<h3 align="center">A multi-agent assistant that triages support tickets, resolves the safe ones and escalates the risky ones to a human</h3>

<p align="center"><i>Submit a ticket. Watch it move through triage, a specialist and a deterministic guardrail. A human reviews anything risky.</i></p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white">
  <img alt="React" src="https://img.shields.io/badge/React-18-20232A?logo=react&logoColor=61DAFB">
  <img alt="Tailwind" src="https://img.shields.io/badge/Tailwind-4-06B6D4?logo=tailwindcss&logoColor=white">
  <img alt="SQLite" src="https://img.shields.io/badge/SQLite-audit%20log-003B57?logo=sqlite&logoColor=white">
  <img alt="Orchestration" src="https://img.shields.io/badge/Orchestration-LangGraph-1C3C3C">
  <img alt="LLM" src="https://img.shields.io/badge/LLM-Groq-F55036">
  <img alt="Tests" src="https://img.shields.io/badge/tests-50%20passing-2F9E6B">
  <img alt="Evals" src="https://img.shields.io/badge/evals-held--out%20set-0A9EDC">
</p>

> **Not a RAG project.** There is no retrieval. The interesting problems here are routing, guardrails, failure handling, human-in-the-loop review and honest evaluation. This is an independent student project that runs locally: it has no authentication, and its datasets are synthetic. See [Limits and honesty notes](#limits-and-honesty-notes).

---

A multi-agent customer-support automation system with a safety-first design. It
triages incoming tickets, routes them to specialist agents, runs a deterministic
guardrail, and either auto-resolves the ticket or escalates it to a human with the
full context. Every step is written to an audit log, and a React console shows the
pipeline running live.

**Stack:** LangGraph, FastAPI, Pydantic, SQLite, Groq (LLM), React (Vite + Tailwind)

---

## Table of contents

1. [What it does](#what-it-does)
2. [Architecture](#architecture)
3. [Design decisions](#design-decisions)
4. [Project structure](#project-structure)
5. [Getting started](#getting-started)
6. [API reference](#api-reference)
7. [Frontend](#frontend)
8. [Evaluation](#evaluation)
9. [Known gaps](#known-gaps)
10. [Roadmap](#roadmap)
11. [Limits and honesty notes](#limits-and-honesty-notes)

---

## What it does

1. A customer message comes in (through the UI or `POST /tickets`).
2. A **triage** agent classifies it: category, sentiment, urgency, confidence and risk flags.
3. A **specialist** agent (billing, technical or account) drafts a reply.
4. A **guardrail**, plain Python with no LLM, decides whether the ticket is safe to
   close automatically. Any risky signal sends it to a human.
5. The ticket is **auto-resolved** or **escalated** with an escalation packet (reasons,
   draft reply, confidence scores). A human then approves, edits or rejects the draft.
6. Every step is stored in an audit log you can replay, stream or export.

The guiding rule is that **the system fails closed**. If the model errors, is unsure,
or the pipeline crashes, the ticket goes to a human. It is never auto-resolved by accident.

---

## Architecture

### System overview

```mermaid
flowchart LR
    UI["React console<br/>(Vite + Tailwind)"] -- "REST + SSE" --> API["FastAPI"]
    API -- "background task" --> SVC["service.process_ticket"]
    SVC --> GRAPH["LangGraph pipeline"]
    GRAPH --> LLM["LLM client<br/>(Groq or offline stub)"]
    SVC -- "writes each event as it happens" --> DB[("SQLite<br/>tickets, events, reviews")]
    API -- "reads / tails events" --> DB
    API -- "SSE: one event per pipeline step" --> UI
```

The pipeline writes each node's event to SQLite **while it runs**, not after. The
stream endpoint simply tails that table. As a result a crash mid-run still leaves a
partial trace, and a page refresh or reconnect resumes from where it left off.

### The pipeline

```mermaid
flowchart TD
    A[intake] --> B[triage<br/>LLM: category, sentiment, urgency,<br/>confidence, risk flags]
    B -->|prompt injection| Q[quarantine<br/>specialists skipped]
    B -->|billing / technical / account| S[specialist<br/>LLM: draft reply + confidence]
    B -->|category: other| G
    S --> G[guardrail<br/>deterministic Python, no LLM]
    Q --> G
    G -->|no rule fired| R[resolve<br/>auto-send reply]
    G -->|any rule fired| E[escalate<br/>build escalation packet]
    E --> H[human review<br/>approve, edit or reject]
```

| Node | Type | Responsibility |
|---|---|---|
| `intake` | code | Normalise whitespace, reset per-run state |
| `triage` | LLM | Category, sentiment, urgency, confidence, `risk_flags` |
| `quarantine` | code | If a prompt injection was flagged, skip the specialists entirely |
| `*_specialist` | LLM | Draft a reply and report confidence and any refund amount it commits to |
| `guardrail` | code | Decide resolve vs escalate, with ordered reasons |
| `resolve` | code | Mark auto-resolved, keep the draft as the final reply |
| `escalate` | code | Build the escalation packet for the reviewer |

### The guardrail

The guardrail is the safety core and deliberately contains **no LLM**. It takes the union
of the model's `risk_flags` and a regex safety net for the highest-stakes patterns (legal
threats, fraud, security, prompt injection, and so on), then adds rules on top:

- Category `other` with no other reason and non-positive sentiment is `ambiguous`.
- A pipeline or LLM error becomes `low_confidence`.
- Triage or specialist confidence below the threshold (default 0.75) is `low_confidence`.
- A refund the draft commits to, or an amount in the text, above the limit (default $200)
  is `refund_over_limit`.
- Negative sentiment with high urgency and no other reason is `angry_customer`.

Reasons are ordered by a fixed priority list, so the first reason is the *primary* reason
shown in the UI. All rules and reason codes are defined in [`docs/policy.md`](docs/policy.md),
the single source of truth for labels, guardrail code and evaluation.

### Data model (SQLite)

```mermaid
erDiagram
    TICKETS ||--o{ EVENTS : "audit log"
    TICKETS ||--o| REVIEWS : "one review"
    TICKETS {
        text id PK
        text text
        text status "processing | auto_resolved | escalated | failed"
        text category
        text primary_reason
        text reasons "JSON list"
        text draft_reply
        text final_reply
        text escalation_packet "JSON"
        text review_action
        text created_at
        text completed_at
    }
    EVENTS {
        int seq "unique per ticket"
        text node
        text at
        text output "JSON"
    }
    REVIEWS {
        text action "approve | edit | reject"
        text reviewer
        text edited_reply
        text note
        text at
    }
```

### Request lifecycle

```mermaid
sequenceDiagram
    participant U as React UI
    participant A as FastAPI
    participant P as Pipeline
    participant D as SQLite
    U->>A: POST /tickets
    A->>D: insert ticket (status processing)
    A-->>U: 202 + ticket id
    A->>P: run in background
    U->>A: GET /tickets/{id}/stream (SSE)
    loop each node
        P->>D: write event
        A->>D: tail new events
        A-->>U: event: trace
    end
    P->>D: set final status
    A-->>U: event: done
    U->>A: POST /tickets/{id}/review (if escalated)
    A->>D: save review + human_review event
```

---

## Design decisions

| Decision | Why |
|---|---|
| **Fail closed** | An LLM error becomes `low_confidence` and escalates. A pipeline crash marks the ticket `failed` (never auto-resolved) and records a `system_error` event. A human can still review it. |
| **Deterministic guardrail** | Safety decisions must be testable and explainable. The LLM only *suggests* risk flags. A regex safety net catches the most dangerous patterns even if the model misses them. |
| **Prompt-injection quarantine** | Ticket text is untrusted. It is wrapped in `<ticket>` tags, and a ticket flagged as injection skips the specialists so attacker-written instructions never reach an agent that drafts refunds. |
| **Audit log by construction** | Events are written as the pipeline runs. The audit trail, the live stream and the trace view all read the same table. |
| **Idempotent submit** | Retrying `POST /tickets` with the same `ticket_id` returns the existing ticket without re-running it. The same id with different text is a 409. |
| **One review per ticket** | A reviewed ticket can't be silently changed. The review is attributed to a named reviewer and logged as an event. |
| **Provider-agnostic LLM client** | Retries with exponential backoff, a call counter and a single `LLMError`. Swap Groq for another provider, or use the offline keyword stub for tests and demos. |
| **Held-out evaluation** | Tuning on the dev set inflates results, so a separately written held-out set is run once per model and never tuned on. |

---

## Project structure

```
SupportGraph/
├── backend/
│   ├── app/
│   │   ├── main.py          # ASGI entry: app = create_app()
│   │   ├── api.py           # FastAPI routes, SSE stream, CORS
│   │   ├── service.py       # runs the pipeline, writes events as they happen
│   │   ├── db.py            # SQLite schema and queries (stdlib sqlite3, WAL)
│   │   ├── graph.py         # LangGraph StateGraph and routing
│   │   ├── nodes.py         # intake, triage, specialists, quarantine, guardrail, resolve, escalate
│   │   ├── guardrail.py     # deterministic rules and regex safety net
│   │   ├── llm.py           # LLM client: retries, backoff, Groq adapter
│   │   ├── stub_llm.py      # offline keyword baseline
│   │   ├── prompts.py       # triage and specialist prompts
│   │   ├── schemas.py       # Pydantic models and enums
│   │   ├── state.py         # shared pipeline state (append-only trace)
│   │   └── config.py        # settings from .env
│   └── tests/               # 50 tests: guardrail rules, routing, fail-closed, API
├── frontend/
│   └── src/
│       ├── pages/           # LiveConsole, ReviewQueue, Audit, Dashboard
│       ├── components/      # Layout, PipelineTrace, JsonView, ui primitives
│       └── lib/             # api client, SSE hook, polling hook, formatting
├── data/
│   ├── tickets_labeled.jsonl    # 100 synthetic dev tickets
│   ├── tickets_heldout.jsonl    # 50 held-out tickets (written in a different style)
│   ├── build_dataset.py, build_heldout.py
│   └── results/                 # saved per-ticket evaluation output
├── scripts/
│   ├── run_pipeline.py      # evaluation runner (resumable)
│   ├── seed_demo.py         # load sample tickets into a running API
│   ├── validate_dataset.py  # label sanity checks
│   └── check_llm.py         # 3-step Groq diagnostic
└── docs/policy.md           # categories and escalation rules (source of truth)
```

---

## Getting started

**Requirements:** Python 3.10+, Node 18+, and a free [Groq API key](https://console.groq.com)
(optional: without one the app runs on the offline stub model).

### 1. Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1     macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt

cp .env.example .env        # then edit .env
cd backend
python -m pytest -q         # 50 tests
python -m uvicorn app.main:app --reload     # http://127.0.0.1:8000  (docs at /docs)
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

### 3. Sample data (optional)

```bash
python scripts/seed_demo.py --limit 30
```

### Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `stub` | `stub` (offline keyword baseline) or `groq` |
| `LLM_MODEL` | `openai/gpt-oss-20b` | Groq model name |
| `GROQ_API_KEY` | | Required when the provider is `groq`. Never commit this file. |
| `CONFIDENCE_THRESHOLD` | `0.75` | Below this, the guardrail escalates as `low_confidence` |
| `REFUND_AUTO_LIMIT_USD` | `200` | Refunds above this always go to a human |
| `MAX_LLM_ATTEMPTS` | `3` | Retries per LLM call before failing closed |
| `DATABASE_PATH` | `support_graph.db` | SQLite file location |
| `CORS_ORIGINS` | Vite dev origins | Allowed browser origins |

The frontend reads `VITE_API_URL` (see `frontend/.env.example`) if the API is not at `http://127.0.0.1:8000`.

---

## API reference

| Endpoint | What it does |
|---|---|
| `GET /health` | Status, provider and model in use |
| `POST /tickets` | Submit `{"text": "...", "ticket_id": "optional"}`. Returns 202 and runs in the background. `?wait=true` runs inline and returns 201. A repeated `ticket_id` returns 200 with `already_existed`. The same id with different text is 409. |
| `GET /tickets` | List tickets. Filter with `?status=`, page with `limit` and `offset`. |
| `GET /tickets/{id}` | Outcome, reasons, draft reply, escalation packet and review |
| `GET /tickets/{id}/trace` | The full audit trail: one event per step, in order |
| `GET /tickets/{id}/stream` | Server-Sent Events: a `trace` event per step, then `done`. Reconnecting with `Last-Event-ID` resumes. |
| `POST /tickets/{id}/review` | `approve`, `edit` or `reject` an escalated or failed ticket. One review per ticket. |
| `GET /stats` | Counts, auto-resolve rate, escalation reasons, review counts, average processing time |

There is **no authentication**. This is a local portfolio project. Do not expose it to the internet.

---

## Frontend

Four screens, built from a Stitch design and wired to the real API:

| Screen | What it shows |
|---|---|
| **Live Console** | Submit a ticket and watch Intake, Triage, Specialist (or Quarantine), Guardrail and Outcome arrive live over SSE |
| **Review Queue** | Escalated and failed tickets, oldest first, with reasons, confidence bars and an editable draft. Approve, edit or reject, attributed to a named reviewer. |
| **Ticket Audit Trail** | Every event for a ticket with expandable raw JSON, time offsets, summary card and copy-as-JSON |
| **Dashboard** | Live counts and charts from `/stats`, plus the offline model-comparison table |

### Live Console
Submit a ticket and watch each pipeline step arrive in real time.

![Live Console](docs/screenshots/live-console.png)

### Review Queue
Escalated tickets with reasons, confidence and an editable draft for the reviewer.

![Review Queue](docs/screenshots/review-queue.png)

### Ticket Audit Trail
Every step of one ticket, with expandable raw output.

![Ticket Audit Trail](docs/screenshots/audit-trail.png)

### Dashboard
Live counts and charts, plus the offline model comparison.

![Dashboard](docs/screenshots/dashboard.png)
---

## Evaluation

The evaluation runs the real pipeline over labeled tickets and compares against the
labels. **Unsafe auto-resolve** (a ticket that should have gone to a human but was closed
automatically) is the metric that matters most.

```bash
python scripts/run_pipeline.py --provider stub --verbose                     # offline baseline
python scripts/run_pipeline.py --provider groq --delay 2.5                   # dev set
python scripts/run_pipeline.py --provider groq --delay 2.5 \
    --dataset data/tickets_heldout.jsonl                                      # held-out set
```

Results are saved per ticket as they finish, so a rate limit or crash never loses
progress. Re-running skips finished tickets (`--fresh` starts over).

### Dev set (100 synthetic tickets, 28 should escalate)

| Metric | Keyword stub | gpt-oss-20b | gpt-oss-120b |
|---|---|---|---|
| Category accuracy | 85% | 93% | 94% |
| Escalation recall | 79% (22/28) | 100% (28/28) | 100% (28/28) |
| Unsafe auto-resolves | 6 | 0 | 0 |
| Over-escalation | 4% | 4% | 6% |
| Primary reason match (strict) | 68% | 86% | 82% |

### Held-out set v1 (50 tickets, 25 should escalate, one run per model)

| Metric | gpt-oss-20b | gpt-oss-120b |
|---|---|---|
| Category accuracy | 90% | 94% |
| Escalation recall | 96% (24/25) | 88% (22/25) |
| Unsafe auto-resolves | 1 | 3 |
| Over-escalation | 12% | 12% |
| Primary reason match (strict) | 88% | 76% |

**How to read this.** Recall dropped from 100% on the dev set to 88-96% on held-out
data, which is exactly why the held-out set exists. With 25 risky tickets the true
recall could plausibly be anywhere between about 70% and 96%, and the gap between the
two models is within run-to-run noise (Groq output is not fully deterministic even at
temperature 0). Neither model is shown to be better, so the cheaper 20b is the default.

---

## Known gaps

Seen in both models on the held-out set. These are the actionable ones:

- Pricing negotiation (volume discounts, seat counts) is not recognised as `sales_enterprise`.
- Credential-recovery actions (2FA reset, email change, ownership transfer) have no
  rule for `identity_verification`.
- Some risky tickets escalate for the wrong reason (for example a disputed invoice
  escalated only as `low_confidence`). Safe, but fragile.
- A Hinglish "payment failed, money deducted" ticket is over-escalated as `angry_customer`,
  and a Spanish "charged twice" ticket was flagged `potential_fraud` while the English
  version was not.
- Knowledge-dependent questions (refund policy, import size limits) escalate as
  `low_confidence` because the specialists have no knowledge source. This caps the
  auto-resolve rate more than model quality does.

The held-out v1 set is now burned for evaluating fixes, so fixes need a fresh set.

---

## Roadmap

- [x] Escalation policy, schemas, labeled dev set
- [x] LangGraph pipeline with three specialists, deterministic guardrail, fail-closed behaviour
- [x] Groq integration and offline stub model
- [x] Prompt-injection quarantine
- [x] Evaluation harness, held-out set and honest reporting
- [x] FastAPI backend with SQLite audit log, live SSE trace and human review
- [x] React console: live trace, review queue, audit trail, dashboard
- [ ] Fix the known gaps above (credential-recovery rule, pricing negotiation, wrong-reason escalations)
- [ ] Fresh held-out v2 set (owner-reviewed labels) to validate the fixes
- [ ] Optional FAQ lookup tool so specialists can answer policy questions
- [ ] Authentication and per-reviewer accounts (out of scope for the portfolio version)
- [ ] Dockerfile and a hosted demo

---

## Limits and honesty notes

- The datasets are **synthetic and self-labeled**. They are a starting point for
  evaluation, not a claim about real-world traffic.
- The guardrail regexes were written while looking at the dev set, so dev numbers are
  optimistic. The held-out numbers are the ones to quote.
- 28 risky dev tickets and 25 risky held-out tickets are small samples. Zero misses
  does not mean a zero miss rate.
- The model-comparison table in the dashboard is static (copied from this README), not
  computed from live traffic.
- No authentication, rate limiting or multi-tenancy. Run it locally.
