"""Sanity-checks the labeled dataset and prints its distribution.

Run:  python scripts/validate_dataset.py
Exits non-zero if the dataset is invalid, so it can gate CI later.
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas import TicketLabel  # noqa: E402

PATH = ROOT / "data" / "tickets_labeled.jsonl"


def main() -> int:
    if not PATH.exists():
        print(f"Missing {PATH}. Run data/build_dataset.py first.")
        return 1

    rows = []
    errors = 0
    for n, line in enumerate(PATH.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            rows.append(TicketLabel.model_validate_json(line))
        except Exception as e:  # noqa: BLE001
            errors += 1
            print(f"Line {n}: {e}")

    ids = [r.id for r in rows]
    texts = [r.text.strip().lower() for r in rows]
    dup_ids = [k for k, v in Counter(ids).items() if v > 1]
    dup_texts = [k for k, v in Counter(texts).items() if v > 1]
    if dup_ids:
        errors += 1
        print("Duplicate ids:", dup_ids)
    if dup_texts:
        errors += 1
        print("Duplicate texts:", dup_texts)

    print(f"\nTotal tickets: {len(rows)}")
    for field in ("category", "sentiment", "urgency"):
        counts = Counter(getattr(r, field).value for r in rows)
        print(f"{field:10}", dict(counts))

    esc = [r for r in rows if r.should_escalate]
    print(f"\nShould escalate: {len(esc)}/{len(rows)} ({len(esc) / len(rows):.0%})")
    print("Max possible auto-resolve rate:", f"{1 - len(esc) / len(rows):.0%}")
    reasons = Counter(r.escalation_reason.value for r in esc)
    print("Escalation reasons:", dict(reasons.most_common()))

    print("\nEscalation rate by category:")
    for cat in ("billing", "technical", "account", "other"):
        sub = [r for r in rows if r.category.value == cat]
        if sub:
            e = sum(r.should_escalate for r in sub)
            print(f"  {cat:10} {e}/{len(sub)}")

    print("\nValidation:", "FAILED" if errors else "OK")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
