"""Wires the nodes into the LangGraph pipeline.

START -> intake -> triage -> (billing | technical | account specialist | guardrail | quarantine)
specialist -> guardrail -> (resolve | escalate) -> END

Tickets triaged as "other" skip the specialists and go straight to the guardrail.
Tickets containing a prompt injection are quarantined: they skip the specialists
too, so attacker-written instructions never reach an agent that can draft
refunds. The guardrail then escalates them.
"""
from langgraph.graph import END, START, StateGraph

from .config import Settings, get_settings
from .guardrail import regex_flags
from .llm import LLMClient, make_llm
from .nodes import SPECIALISTS, build_nodes
from .state import TicketState

# Flags that mean "do not let any specialist see this ticket".
QUARANTINE_FLAGS = {"prompt_injection"}


def is_quarantined(state: TicketState) -> bool:
    flags = set(state.get("risk_flags", []) or []) | set(regex_flags(state.get("raw_text", "") or ""))
    return bool(QUARANTINE_FLAGS & flags)


def route_after_triage(state: TicketState) -> str:
    if is_quarantined(state):
        return "quarantine"
    category = state.get("category", "other")
    return f"{category}_specialist" if category in SPECIALISTS else "guardrail"


def route_after_guardrail(state: TicketState) -> str:
    return "resolve" if state.get("guardrail_decision") == "resolve" else "escalate"


def build_graph(llm: LLMClient | None = None, settings: Settings | None = None):
    settings = settings or get_settings()
    llm = llm or make_llm(settings)
    nodes = build_nodes(llm, settings)

    g = StateGraph(TicketState)
    for name, fn in nodes.items():
        g.add_node(name, fn)

    g.add_edge(START, "intake")
    g.add_edge("intake", "triage")
    g.add_conditional_edges(
        "triage",
        route_after_triage,
        {
            **{f"{c}_specialist": f"{c}_specialist" for c in SPECIALISTS},
            "guardrail": "guardrail",
            "quarantine": "quarantine",
        },
    )
    for c in SPECIALISTS:
        g.add_edge(f"{c}_specialist", "guardrail")
    g.add_edge("quarantine", "guardrail")
    g.add_conditional_edges(
        "guardrail", route_after_guardrail, {"resolve": "resolve", "escalate": "escalate"}
    )
    g.add_edge("resolve", END)
    g.add_edge("escalate", END)
    return g.compile()


def run_ticket(graph, ticket_id: str, text: str) -> TicketState:
    """Run one ticket through the pipeline and return the final state."""
    return graph.invoke({"ticket_id": ticket_id, "raw_text": text, "trace": []})
