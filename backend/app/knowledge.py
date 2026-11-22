"""Structured product facts and the lookup tools that read them.

This is deliberately NOT retrieval. There is no embedding, no similarity search and no free
text index. Facts live in typed tables, and an agent can only ask for them through a closed
set of tools with enumerated arguments. A bad tool name or argument is rejected, never guessed.

The product, its plans and its prices are fictional. They exist so the agents have one
authoritative source to quote, instead of inventing prices and timelines.
"""
from dataclasses import dataclass
from typing import Callable, Literal

PlanName = Literal["free", "pro", "team", "enterprise"]

PLANS: dict[str, dict] = {
    "free": {"price": "$0", "members": "up to 3 members", "history": "7 days of history", "api_per_min": 60,
             "extra": "Community support only."},
    "pro": {"price": "$12 per user per month ($10 per user per month billed annually)", "members": "unlimited members",
            "history": "unlimited history", "api_per_min": 600,
            "extra": "Includes a 14-day free trial with no card required. Email support."},
    "team": {"price": "$24 per user per month ($20 per user per month billed annually)", "members": "minimum 5 seats",
             "history": "unlimited history", "api_per_min": 1800,
             "extra": "Adds shared workspaces, roles and permissions, SSO and priority support. There is no automatic volume discount."},
    "enterprise": {"price": "custom pricing, set by the sales team", "members": "custom seat count",
                   "history": "unlimited history", "api_per_min": 6000,
                   "extra": "Quotes, annual contracts and PO-based invoicing are handled by sales, not by support."},
}

REFUND = (
    "Monthly plans can be refunded within 7 days of the charge. Annual plans can be refunded within 14 days of the charge. "
    "Support can approve refunds up to $200 on its own; anything above $200 needs a human reviewer. "
    "Approved refunds go back to the original payment method in 5 to 10 business days."
)

PAYMENT_METHODS = (
    "Accepted: Visa, Mastercard, American Express and PayPal in all currencies; UPI and net banking for INR only. "
    "Invoice and purchase-order payment is available on Enterprise only. "
    "Billing currencies: USD, EUR, GBP and INR. The currency is fixed at the first purchase; support has to review a request to change it."
)

BILLING_HOWTO: dict[str, str] = {
    "invoices": "Invoices are under Settings > Billing > Invoices, where each one can be downloaded as a PDF. Company name and tax ID can be edited under Settings > Billing > Billing details, and invoices from the last 90 days can be reissued after the change.",
    "seats": "Seats are changed under Settings > Billing > Seats. Added seats are charged immediately, prorated for the rest of the billing period. Removed seats take effect at the next renewal.",
    "trial": "Pro has a 14-day free trial with no card required. Upgrading is under Settings > Billing > Change plan, and it takes effect immediately.",
    "currency": "The billing currency is fixed at the first purchase. A currency change request needs a support review.",
    "tax_id": "A tax ID such as GST or VAT can be added under Settings > Billing > Billing details. It applies to future invoices, and invoices from the last 90 days can be reissued.",
}

ACCOUNT_HOWTO: dict[str, str] = {
    "two_factor": "Two-factor authentication is turned on under Settings > Security > Two-factor authentication, using an authenticator app. Ten one-time backup codes are shown when it is enabled. Support cannot disable 2FA for someone who has lost both their device and their backup codes without identity verification.",
    "change_email": "The account email is changed under Settings > Account > Email. A confirmation link is sent to the new address and the change applies once it is confirmed.",
    "invite_member": "Admins invite people under Settings > Members > Invite. Invitations expire after 7 days and can be resent.",
    "password_reset": "On the login page, choose Forgot password. A reset link is emailed and stays valid for 60 minutes.",
    "export_data": "Admins can export workspace data as CSV or JSON under Settings > Data > Export. Large exports are emailed as a download link that stays valid for 7 days.",
}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    run: Callable[[str | None], str]
    arg_name: str | None  # "plan", "topic" or None
    allowed: tuple[str, ...] = ()


def _plan(arg: str | None) -> str:
    p = PLANS[arg]
    return (f"{arg.title()} plan: {p['price']}; {p['members']}; {p['history']}; API limit {p['api_per_min']} requests per minute. {p['extra']}")


def _api(arg: str | None) -> str:
    return f"{arg.title()} plan API limit: {PLANS[arg]['api_per_min']} requests per minute."


TOOLS: dict[str, Tool] = {t.name: t for t in (
    Tool("get_plan_details", "Price, seats, history and features of one plan.", _plan, "plan", tuple(PLANS)),
    Tool("get_api_limits", "API requests-per-minute limit of one plan.", _api, "plan", tuple(PLANS)),
    Tool("get_refund_policy", "Refund windows, the auto-approval limit and refund timing.", lambda _a: REFUND, None),
    Tool("get_payment_methods", "Accepted payment methods and billing currencies.", lambda _a: PAYMENT_METHODS, None),
    Tool("get_billing_howto", "Steps for invoices, seats, trial, currency or tax ID.", lambda a: BILLING_HOWTO[a], "topic", tuple(BILLING_HOWTO)),
    Tool("get_account_howto", "Steps for two-factor, email change, invitations, password reset or data export.", lambda a: ACCOUNT_HOWTO[a], "topic", tuple(ACCOUNT_HOWTO)),
)}

ToolName = Literal["get_plan_details", "get_api_limits", "get_refund_policy", "get_payment_methods", "get_billing_howto", "get_account_howto"]


def tool_menu() -> str:
    lines = []
    for t in TOOLS.values():
        arg = f"({t.arg_name}: {' | '.join(t.allowed)})" if t.arg_name else "()"
        lines.append(f"  - {t.name}{arg}: {t.description}")
    return "\n".join(lines)


def run_lookup(tool: str, arg: str | None) -> dict:
    """Execute one lookup. Unknown tool or argument returns ok=False; nothing is guessed."""
    t = TOOLS.get(tool)
    if t is None:
        return {"tool": tool, "arg": arg, "ok": False, "error": "unknown tool"}
    if t.arg_name is None:
        arg = None
    elif arg not in t.allowed:
        return {"tool": tool, "arg": arg, "ok": False, "error": f"{t.arg_name} must be one of {', '.join(t.allowed)}"}
    return {"tool": tool, "arg": arg, "ok": True, "text": t.run(arg)}
