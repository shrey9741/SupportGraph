"""Shared state that flows through every node.

Values are plain strings/numbers (enum .value) so the state is JSON-safe.
`trace` is append-only (reducer = list concatenation): every node adds one
event, which is the audit log for the ticket.
"""
import operator
from typing import Annotated, Any, TypedDict


class TicketState(TypedDict, total=False):
    ticket_id: str
    raw_text: str
    # triage
    category: str
    sentiment: str
    urgency: str
    triage_confidence: float
    risk_flags: list[str]
    # specialist
    specialist_used: str | None
    draft_reply: str | None
    specialist_confidence: float | None
    commits_to_refund_usd: float | None
    # guardrail + outcome
    guardrail_decision: str
    guardrail_reasons: list[str]
    final_outcome: str
    final_reply: str | None
    escalation_packet: dict[str, Any] | None
    error: str | None
    # audit log
    trace: Annotated[list[dict[str, Any]], operator.add]
