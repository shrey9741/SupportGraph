# SupportGraph

A multi-agent customer success automation system. It triages support tickets,
routes them to specialist agents, applies a guardrail, and either auto-resolves
or escalates to a human with full context.

**Stack:** LangGraph, FastAPI, Pydantic, SQLite, React (Vite + Tailwind)

## Status

- [x] Day 1: repo scaffold, escalation policy, schemas, labeled seed dataset (100 tickets)
- [ ] Day 2: LangGraph core pipeline (intake, triage, one specialist, guardrail)
- [ ] Specialists 2 and 3, resolve and escalate nodes
- [ ] FastAPI backend and SQLite audit log
- [ ] React frontend with live trace
- [ ] Evaluation harness and dashboard

## Layout

```
backend/app/     schemas and (soon) the LangGraph pipeline
data/            labeled tickets (tickets_labeled.jsonl) and the builder script
docs/policy.md   single source of truth for labels and guardrail rules
scripts/         dataset validation, eval runner (soon)
frontend/        React app (soon)
```

## Setup

```bash
pip install -r backend/requirements.txt
cp .env.example .env        # add your API key
python data/build_dataset.py
python scripts/validate_dataset.py
```

## Notes

The seed dataset is hand-labeled and synthetic. It is a starting point for
evaluation, not a claim about real-world traffic.
