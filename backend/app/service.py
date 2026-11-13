"""Runs a ticket through the graph and writes every node's event to the audit log
as it happens (not after the run), so a crash mid-run still leaves a partial trace
and the live stream can tail it."""
from typing import Any

from . import db


def process_ticket(graph, db_path: str, ticket_id: str, text: str) -> None:
    seq = 0
    acc: dict[str, Any] = {}
    try:
        for chunk in graph.stream(
            {"ticket_id": ticket_id, "raw_text": text, "trace": []}, stream_mode="updates"
        ):
            for _node, update in chunk.items():
                update = update or {}
                acc.update({k: v for k, v in update.items() if k != "trace"})
                events = update.get("trace", [])
                if events:
                    with db.session(db_path) as conn:
                        for ev in events:
                            seq += 1
                            db.add_event(conn, ticket_id, seq, ev)
    except Exception as e:  # noqa: BLE001  unexpected crash: fail closed, keep the evidence
        with db.session(db_path) as conn:
            db.add_event(conn, ticket_id, seq + 1, {
                "node": "system_error", "at": db.now(),
                "output": {"error": f"{type(e).__name__}: {e}"},
            })
            db.fail_ticket(conn, ticket_id, f"{type(e).__name__}: {e}")
        return

    outcome = acc.get("final_outcome")
    with db.session(db_path) as conn:
        if outcome in ("auto_resolved", "escalated"):
            db.complete_ticket(conn, ticket_id, outcome, acc)
        else:
            db.add_event(conn, ticket_id, seq + 1, {
                "node": "system_error", "at": db.now(),
                "output": {"error": "pipeline ended without an outcome"},
            })
            db.fail_ticket(conn, ticket_id, "pipeline ended without an outcome")
