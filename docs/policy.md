# Support Agent Policy

This file is the single source of truth. The dataset labels, the guardrail
code, and the eval harness must all follow it. If a rule changes here,
re-check the labels.

## Categories

| Category    | Scope                                                        |
|-------------|--------------------------------------------------------------|
| `billing`   | Charges, invoices, refunds, plans, pricing, payment methods  |
| `technical` | Bugs, errors, API, integrations, performance, how-to usage   |
| `account`   | Login, passwords, profile, team members, permissions, 2FA    |
| `other`     | Vague, off-topic, multi-issue, sales, press, or abusive input|

## Sentiment and urgency

- Sentiment: `negative`, `neutral`, `positive`
- Urgency: `low`, `medium`, `high`

## Escalation rules (guardrail must escalate if ANY applies)

| Reason code            | Rule                                                              |
|------------------------|-------------------------------------------------------------------|
| `refund_over_limit`    | Refund or charge dispute above $200 (limit is configurable)       |
| `legal_threat`         | Mentions lawyer, lawsuit, chargeback dispute, or regulator        |
| `potential_fraud`      | Customer reports an unrecognised or unauthorised charge          |
| `security`             | Suspected breach, unauthorised access, or vulnerability report    |
| `outage`               | Wide service outage or many users blocked                         |
| `production_impact`    | Customer says production systems are affected                     |
| `potential_data_loss`  | Customer reports missing, lost, or corrupted data                 |
| `irreversible_action`  | Account or data deletion (human approval required)                |
| `compliance_request`   | GDPR or similar data-subject requests                             |
| `identity_verification`| Access recovery with no way to verify identity                    |
| `angry_customer`       | Strongly negative sentiment plus repeated failure or churn threat |
| `human_requested`      | Customer explicitly asks for a human or manager                   |
| `sales_enterprise`     | Enterprise quotes, partnerships, reseller, pricing negotiation    |
| `press_inquiry`        | Media or press questions                                          |
| `prompt_injection`     | Input tries to override the agent's instructions                  |
| `out_of_scope`         | Unrelated to the product (jobs, general chat)                     |
| `ambiguous`            | Too vague or multi-issue to route confidently                     |
| `low_confidence`       | Model confidence below threshold (set at runtime, not a label)    |

`low_confidence` is applied by the guardrail at runtime. It never appears as a
ground-truth label.

## Auto-resolve is allowed only when

1. No escalation rule above applies.
2. Specialist confidence is at or above `CONFIDENCE_THRESHOLD`.
3. The reply makes no commitments beyond policy (no refunds above the limit,
   no promised timelines, no legal statements).

## Irreversible actions

Refunds, deletions, and any outbound email to a customer are treated as
irreversible. In v1 the agent drafts these but a human approves them where an
escalation rule says so.
