"""LangGraph node functions. Each returns a partial state update plus one trace event.

Fail-safe rule: if an LLM step fails after its retries, the node records the
error and the guardrail escalates the ticket. A failure never auto-resolves.
"""
from datetime import datetime, timezone
from typing import Any, Callable

from .config import Settings
from .guardrail import evaluate
from .llm import LLMClient, LLMError
from .prompts import TRIAGE_SYSTEM, specialist_system
from .schemas import SpecialistOutput, TriageOutput
from .state import TicketState

SPECIALISTS = ("billing", "technical", "account")


def _event(node: str, output: dict[str, Any]) -> dict[str, Any]:
    return {
        "node": node,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "output": output,
    }


def _wrap(text: str) -> str:
    return f"<ticket>\n{text}\n</ticket>"


def build_nodes(llm: LLMClient, settings: Settings) -> dict[str, Callable[[TicketState], dict]]:
    def intake(state: TicketState) -> dict:
        text = " ".join((state.get("raw_text") or "").split())
        update = {
            "raw_text": text,
            "risk_flags": [],
            "specialist_used": None,
            "draft_reply": None,
            "error": None,
        }
        update["trace"] = [_event("intake", {"ticket_id": state.get("ticket_id"), "chars": len(text)})]
        return update

    def triage(state: TicketState) -> dict:
        try:
            out = llm.structured(TriageOutput, TRIAGE_SYSTEM, _wrap(state["raw_text"]))
            update: dict[str, Any] = {
                "category": out.category.value,
                "sentiment": out.sentiment.value,
                "urgency": out.urgency.value,
                "triage_confidence": out.confidence,
                "risk_flags": [f.value for f in out.risk_flags],
            }
        except LLMError as e:
            update = {
                "category": "other",
                "sentiment": "neutral",
                "urgency": "medium",
                "triage_confidence": 0.0,
                "risk_flags": [],
                "error": f"triage failed: {e}",
            }
        update["trace"] = [_event("triage", dict(update))]
        return update

    def make_specialist(category: str) -> Callable[[TicketState], dict]:
        name = f"{category}_specialist"
        system = specialist_system(category)

        def node(state: TicketState) -> dict:
            try:
                out = llm.structured(SpecialistOutput, system, _wrap(state["raw_text"]))
                update: dict[str, Any] = {
                    "specialist_used": name,
                    "draft_reply": out.draft_reply,
                    "specialist_confidence": out.confidence,
                    "commits_to_refund_usd": out.commits_to_refund_usd,
                }
            except LLMError as e:
                update = {
                    "specialist_used": name,
                    "draft_reply": None,
                    "specialist_confidence": 0.0,
                    "commits_to_refund_usd": None,
                    "error": f"{name} failed: {e}",
                }
            update["trace"] = [_event(name, dict(update))]
            return update

        return node

    def quarantine(state: TicketState) -> dict:
        # Visible in the audit trace so a human can see why no specialist ran.
        return {"trace": [_event("quarantine", {"reason": "prompt_injection", "specialist_skipped": True})]}

    def guardrail(state: TicketState) -> dict:
        result = evaluate(
            state,
            confidence_threshold=settings.confidence_threshold,
            refund_limit_usd=settings.refund_auto_limit_usd,
        )
        update = {
            "guardrail_decision": result.decision,
            "guardrail_reasons": result.reasons,
        }
        update["trace"] = [_event("guardrail", dict(update))]
        return update

    def resolve(state: TicketState) -> dict:
        update = {
            "final_outcome": "auto_resolved",
            "final_reply": state.get("draft_reply"),
        }
        update["trace"] = [_event("resolve", {"has_reply": bool(update["final_reply"])})]
        return update

    def escalate(state: TicketState) -> dict:
        reasons = state.get("guardrail_reasons", [])
        packet = {
            "ticket_id": state.get("ticket_id"),
            "text": state.get("raw_text"),
            "category": state.get("category"),
            "sentiment": state.get("sentiment"),
            "urgency": state.get("urgency"),
            "primary_reason": reasons[0] if reasons else None,
            "all_reasons": reasons,
            "draft_reply": state.get("draft_reply"),
            "specialist_confidence": state.get("specialist_confidence"),
            "triage_confidence": state.get("triage_confidence"),
            "error": state.get("error"),
        }
        update = {"final_outcome": "escalated", "escalation_packet": packet}
        update["trace"] = [_event("escalate", {"primary_reason": packet["primary_reason"]})]
        return update

    nodes: dict[str, Callable[[TicketState], dict]] = {
        "intake": intake,
        "triage": triage,
        "quarantine": quarantine,
        "guardrail": guardrail,
        "resolve": resolve,
        "escalate": escalate,
    }
    for cat in SPECIALISTS:
        nodes[f"{cat}_specialist"] = make_specialist(cat)
    return nodes
