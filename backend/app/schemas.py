"""Shared schemas. Used by the dataset, the LangGraph nodes, and the API.

Keep these strict: every field typed, every enum closed. Malformed LLM output
should fail validation and trigger a retry, never pass through silently.
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class Category(str, Enum):
    billing = "billing"
    technical = "technical"
    account = "account"
    other = "other"


class Sentiment(str, Enum):
    negative = "negative"
    neutral = "neutral"
    positive = "positive"


class Urgency(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class EscalationReason(str, Enum):
    refund_over_limit = "refund_over_limit"
    legal_threat = "legal_threat"
    potential_fraud = "potential_fraud"
    security = "security"
    outage = "outage"
    production_impact = "production_impact"
    potential_data_loss = "potential_data_loss"
    irreversible_action = "irreversible_action"
    compliance_request = "compliance_request"
    identity_verification = "identity_verification"
    angry_customer = "angry_customer"
    human_requested = "human_requested"
    sales_enterprise = "sales_enterprise"
    press_inquiry = "press_inquiry"
    prompt_injection = "prompt_injection"
    out_of_scope = "out_of_scope"
    ambiguous = "ambiguous"
    # Runtime only, never a ground-truth label:
    low_confidence = "low_confidence"


class TicketLabel(BaseModel):
    """One ground-truth row in data/tickets_labeled.jsonl."""

    id: str
    text: str = Field(min_length=1)
    category: Category
    sentiment: Sentiment
    urgency: Urgency
    should_escalate: bool
    escalation_reason: Optional[EscalationReason] = None

    @model_validator(mode="after")
    def check_escalation_consistency(self):
        if self.should_escalate and self.escalation_reason is None:
            raise ValueError("should_escalate=True requires an escalation_reason")
        if not self.should_escalate and self.escalation_reason is not None:
            raise ValueError("escalation_reason set but should_escalate=False")
        if self.escalation_reason == EscalationReason.low_confidence:
            raise ValueError("low_confidence is runtime-only, not a valid label")
        return self


class TriageOutput(BaseModel):
    """What the triage agent must return (validated, retried on failure)."""

    category: Category
    sentiment: Sentiment
    urgency: Urgency
    confidence: float = Field(ge=0.0, le=1.0)


class SpecialistOutput(BaseModel):
    """What each specialist agent must return."""

    draft_reply: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    commits_to_refund_usd: Optional[float] = Field(default=None, ge=0)
