"""Keyword-based stand-in for an LLM.

Purpose: (1) lets the graph, guardrail and API be built and tested with zero
API calls, and (2) acts as a naive baseline the real model must beat in the
evaluation. It is intentionally simple and will make mistakes.
"""
import re

from .llm import LLMClient
from .schemas import SpecialistOutput, TriageOutput

BILLING_KW = (
    "charge", "charged", "invoice", "refund", "billing", "billed", "payment",
    "plan", "pricing", "price", "subscription", "coupon", "receipt", "credit card",
    "tax", "gst", "discount", "trial", "seats", "upgrade", "annual", "monthly",
    "fee", "paying", "bill",
)
TECH_KW = (
    "error", "crash", "api", "webhook", "bug", "export", "import", "integration",
    "slow", "load times", "sso", "sdk", "browser", "chart", "sync", "csv", "upload",
    "dashboard", "mobile app", "battery", "connector", "database", "search",
    "notification", "excel", "status page", "service is down", "editor", "shortcut",
    "dark mode", "share button", "okta", "slack", "zapier", "oauth", "python",
)
ACCT_KW = (
    "password", "login", "log in", "logged", "account", "workspace", "two-factor",
    "2fa", "teammate", "team member", "invite", "username", "display name",
    "email address", "timezone", "verification code", "sms", "permission", "role",
    "admin", "merge", "ownership", "deactivate",
)
NEG_KW = (
    "unacceptable", "terrible", "awful", "joke", "annoying", "angry", "worst",
    "furious", "!!", "leaving", "lawyer", "disput", "never authorized",
)
POS_KW = ("thanks", "thank you", "love", "great", "awesome")
HIGH_KW = (
    "urgent", "immediately", "asap", "production", "service is down", "locked out",
    "lost", "missing", "unauthorized", "fraud", "lawyer", "!!",
)
MED_KW = ("error", "failed", "can't", "cannot", "not working", "crash", "charged twice")

AMOUNT_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)")

REPLIES = {
    "billing": "Thanks for reaching out about billing. I've looked at your request and can help with that. You can find invoices, plans and payment methods under Settings > Billing. If anything looks wrong there, reply with the invoice date and I'll check it.",
    "technical": "Thanks for the details. For this kind of issue, please try refreshing, clearing your cache and checking our docs. If it keeps happening, reply with your browser, steps to reproduce and any error text so we can investigate.",
    "account": "Thanks for contacting us about your account. You can manage this from Settings > Account. If you run into trouble, reply with the email on the account and we'll guide you through the next step.",
}


def _count(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for w in words if w in text)


def _ticket_text(user: str) -> str:
    m = re.search(r"<ticket>\s*(.*?)\s*</ticket>", user, re.S)
    return (m.group(1) if m else user).strip()


class StubLLM(LLMClient):
    def __init__(self):
        super().__init__(max_attempts=1, backoff_s=0.0)

    def _call(self, schema, system, user):
        text = _ticket_text(user)
        if schema is TriageOutput:
            return self._triage(text)
        if schema is SpecialistOutput:
            return self._specialist(text, system)
        raise ValueError(f"StubLLM cannot produce {schema.__name__}")

    def _triage(self, text: str) -> TriageOutput:
        t = text.lower()
        scores = {
            "billing": _count(t, BILLING_KW),
            "technical": _count(t, TECH_KW),
            "account": _count(t, ACCT_KW),
        }
        best = max(scores, key=lambda k: scores[k])
        hits = scores[best]
        category = best if hits > 0 else "other"

        if _count(t, NEG_KW):
            sentiment = "negative"
        elif _count(t, POS_KW):
            sentiment = "positive"
        else:
            sentiment = "neutral"

        if _count(t, HIGH_KW):
            urgency = "high"
        elif _count(t, MED_KW):
            urgency = "medium"
        else:
            urgency = "low"

        if category == "other":
            confidence = 0.85 if sentiment == "positive" else 0.5
        else:
            confidence = 0.9 if hits >= 2 else 0.8

        flags = []
        if "production" in t:
            flags.append("production_impact")
        if re.search(r"(service|site|platform) is down", t):
            flags.append("outage")
        if re.search(r"(lost|missing|disappeared).{0,40}(data|work|fields|reports)|lose my data", t):
            flags.append("potential_data_loss")

        return TriageOutput(
            category=category,
            sentiment=sentiment,
            urgency=urgency,
            confidence=confidence,
            risk_flags=flags,
        )

    def _specialist(self, text: str, system: str) -> SpecialistOutput:
        category = next((c for c in REPLIES if f"{c}:" in system), "billing")
        commits = None
        amounts = [float(a.replace(",", "")) for a in AMOUNT_RE.findall(text)]
        if amounts and "refund" in text.lower():
            commits = max(amounts)
        return SpecialistOutput(
            draft_reply=REPLIES[category],
            confidence=0.9,
            commits_to_refund_usd=commits,
        )
