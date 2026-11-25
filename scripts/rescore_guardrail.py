"""Post-hoc check: re-run ONLY the current guardrail's figure check on replies saved in a results file.

    python scripts/rescore_guardrail.py data/results/groq_openai-gpt-oss-120b__tickets_heldout_v4.jsonl \
        data/tickets_heldout_v4.jsonl

No model is called. This is an analysis of saved replies, NOT a new evaluation run: it shows which saved
escalations came from the figure check and whether they still would after a guardrail fix. Report it as
post-hoc, next to the original numbers, never in place of them.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.guardrail import ungrounded_figures  # noqa: E402
from app.knowledge import run_lookup  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    results = [json.loads(l) for l in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
    tickets = {r["id"]: r for r in map(json.loads, Path(sys.argv[2]).read_text(encoding="utf-8").splitlines())}
    changed = 0
    for r in results:
        reply = r.get("reply")
        if not reply:
            continue
        facts = [run_lookup(l["tool"], l.get("arg")).get("text", "") for l in r.get("lookups", [])]
        bad = ungrounded_figures(reply, tickets[r["id"]]["text"], facts)
        old = next((e["output"].get("ungrounded_figures") for e in r.get("trace", []) if e["node"] == "guardrail"), None) or []
        if sorted(old) != sorted(bad):
            changed += 1
            print(f'{r["id"]}: flagged then {old} -> flagged now {bad}')
    print(f"\n{changed} ticket(s) whose figure check changes. Other reasons for escalation are not re-evaluated here.")


if __name__ == "__main__":
    main()
