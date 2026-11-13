"""Deterministic guardrail. Plain Python, no LLM, fully unit-testable.

Escalate if ANY rule fires. Rules follow docs/policy.md:
1. Risk flags from the triage model, plus a regex safety net for high-stakes
   patterns the model might miss (defence in depth).
2. Category "other" escalates unless it is a benign closing message.
3. Low confidence from triage or the specialist, or any upstream LLM error.
4. Refund commitments or refund/charge amounts above the auto limit.
5. Negative sentiment with high urgency and no other explanation.
"""
import re
from dataclasses import dataclass
from typing import Any, Mapping

# Reasons are returned sorted by this priority; the first is the "primary" reason.
PRIORITY = [
    "security", "legal_threat", "potential_fraud", "outage", "production_impact",
    "potential_data_loss", "refund_over_limit", "irreversible_action",
    "compliance_request", "identity_verification", "prompt_injection",
    "human_requested", "press_inquiry", "sales_enterprise", "out_of_scope",
    "angry_customer", "ambiguous", "low_confidence",
]

_PATTERNS: dict[str, re.Pattern[str]] = {
    "prompt_injection": re.compile(
        r"ignore (all |any )?(previous|prior|above|earlier) (instructions|prompts?)"
        r"|disregard (all |any )?(previous|prior|your) instructions"
        r"|(disregard|forget|override|bypass) (all |any |the |your )?(previous |prior |above )?"
        r"(rules|instructions|guidelines|polic(y|ies))"
        r"|\b(admin|developer|debug|god) mode\b"
        r"|i('| a)m your (developer|creator|admin(istrator)?)"
        r"|reveal (your )?system prompt",
        re.I,
    ),
    "legal_threat": re.compile(
        r"\b(lawyer|attorney|lawsuit|legal action|chargeback)\b|\bsue (you|your|the company)\b",
        re.I,
    ),
    "human_requested": re.compile(
        r"\b(speak|talk|escalate) to (a |the |your )?(manager|human|real person|supervisor|agent)\b"
        r"|\bcall me\b|\bcall (me )?back\b"
        r"|\bescalate (this |it )?to (someone|somebody) (senior|higher|in charge)"
        r"|\b(speak|talk) to (someone|somebody) (senior|in charge)",
        re.I,
    ),
    "sales_enterprise": re.compile(
        r"volume discount|bulk (pricing|discount)|custom (quote|pricing|contract)"
        r"|enterprise (plan|quote|pricing|contract)|reseller|affiliate program"
        r"|partner(ship)? with (you|your)",
        re.I,
    ),
    "identity_verification": re.compile(
        r"\b(can|could|would|will) you (please )?(reset|disable|remove|turn off|bypass)\b"
        r".{0,30}\b(2fa|two[- ]factor|mfa|authenticator)"
        r"|\b(lost|broke|broken|stolen) (my )?(phone|device|authenticator|backup codes)\b"
        r".{0,60}\b(2fa|two[- ]factor|mfa|codes?|log ?in|access)"
        r"|\bformer admin\b|no access to the (admin|owner)'?s? email",
        re.I,
    ),
    "compliance_request": re.compile(r"\b(gdpr|ccpa|data subject)\b", re.I),
    "irreversible_action": re.compile(
        r"\bdelete (my|our) (account|workspace|data)\b|\bdelete all (my|our) data\b", re.I
    ),
    "press_inquiry": re.compile(r"\b(journalist|reporter|newspaper)\b", re.I),
    "potential_fraud": re.compile(
        r"\bfraud(ulent)?\b|\b(unknown|unrecogni[sz]ed|unauthori[sz]ed) charge\b", re.I
    ),
    "security": re.compile(
        r"\bsecurity vulnerabilit(y|ies)\b"
        r"|\b(someone|somebody) (logged|signed) into my account\b"
        r"|\bunauthori[sz]ed access\b|\bhacked\b",
        re.I,
    ),
}

_AMOUNT_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)")
_MONEY_WORDS_RE = re.compile(
    r"\b(refund(ed)?|billed|charged?|dispute|disputing|reimburse|overcharg\w*|discrepanc\w*"
    r"|billing error|wrong amount|incorrect (amount|charge|invoice)|(doesn'?t|does not) match)\b",
    re.I,
)


@dataclass
class GuardrailDecision:
    decision: str  # "resolve" | "escalate"
    reasons: list[str]


def regex_flags(text: str) -> list[str]:
    return [name for name, pat in _PATTERNS.items() if pat.search(text)]


def amounts_usd(text: str) -> list[float]:
    return [float(a.replace(",", "")) for a in _AMOUNT_RE.findall(text)]


def evaluate(
    state: Mapping[str, Any],
    *,
    confidence_threshold: float = 0.75,
    refund_limit_usd: float = 200.0,
) -> GuardrailDecision:
    text = state.get("raw_text", "") or ""
    category = state.get("category", "other")
    sentiment = state.get("sentiment", "neutral")
    urgency = state.get("urgency", "low")
    draft = state.get("draft_reply") or ""

    # Union of the model's flags and the regex safety net. low_confidence is
    # only ever decided here, never taken from the model.
    reasons = set(state.get("risk_flags", []) or []) | set(regex_flags(text))
    reasons.discard("low_confidence")

    if category == "other" and not reasons and sentiment != "positive":
        reasons.add("ambiguous")

    # Fail closed: any upstream LLM error escalates.
    if state.get("error"):
        reasons.add("low_confidence")

    if float(state.get("triage_confidence", 0.0) or 0.0) < confidence_threshold:
        reasons.add("low_confidence")

    # Only demand specialist confidence if a specialist actually ran. A failed
    # specialist still sets specialist_used (and error), so it stays fail-closed.
    if category != "other" and state.get("specialist_used"):
        spec_conf = state.get("specialist_confidence")
        if spec_conf is None or float(spec_conf) < confidence_threshold:
            reasons.add("low_confidence")

    commits = state.get("commits_to_refund_usd")
    if commits is not None and float(commits) > refund_limit_usd:
        reasons.add("refund_over_limit")

    ticket_amounts = amounts_usd(text)
    if ticket_amounts and _MONEY_WORDS_RE.search(text) and max(ticket_amounts) > refund_limit_usd:
        reasons.add("refund_over_limit")

    draft_amounts = amounts_usd(draft)
    if draft_amounts and re.search("refund", draft, re.I) and max(draft_amounts) > refund_limit_usd:
        reasons.add("refund_over_limit")

    if not reasons and sentiment == "negative" and urgency == "high":
        reasons.add("angry_customer")

    if not reasons:
        return GuardrailDecision("resolve", [])

    ordered = sorted(
        reasons, key=lambda r: PRIORITY.index(r) if r in PRIORITY else len(PRIORITY)
    )
    return GuardrailDecision("escalate", ordered)
