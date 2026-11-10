"""Run the SupportGraph pipeline over the labeled dataset and print metrics.

Examples (from the project root):
  python scripts/run_pipeline.py                      # provider from .env (default: stub)
  python scripts/run_pipeline.py --provider groq      # real model
  python scripts/run_pipeline.py --limit 10 --verbose
  python scripts/run_pipeline.py --provider groq --delay 2.5   # slow down for rate limits

Results are appended to data/results/<provider>_<model>.jsonl as each ticket
finishes, so a crash or rate limit never loses progress. Re-running skips
tickets already done. Use --fresh to start over.
"""
import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.graph import build_graph, run_ticket  # noqa: E402
from app.llm import make_llm  # noqa: E402
from app.schemas import TicketLabel  # noqa: E402

DATA = ROOT / "data" / "tickets_labeled.jsonl"
RESULTS_DIR = ROOT / "data" / "results"


def load_labels(path: Path = DATA) -> list[TicketLabel]:
    return [TicketLabel.model_validate_json(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def pct(n: float, d: float) -> str:
    return f"{n / d:.0%}" if d else "n/a"


def print_metrics(labels: list[TicketLabel], results: dict[str, dict]) -> None:
    rows = [(l, results[l.id]) for l in labels if l.id in results]
    n = len(rows)
    if not n:
        print("No results to score.")
        return

    cat_ok = sum(l.category.value == r["category"] for l, r in rows)
    esc = [(l, r) for l, r in rows if l.should_escalate]
    non = [(l, r) for l, r in rows if not l.should_escalate]
    escalated = lambda r: r["outcome"] == "escalated"  # noqa: E731

    unsafe = [(l, r) for l, r in esc if not escalated(r)]       # should escalate, but auto-resolved
    over = [(l, r) for l, r in non if escalated(r)]             # should resolve, but escalated
    caught = len(esc) - len(unsafe)
    reason_ok = sum(
        1 for l, r in esc if escalated(r) and r["primary_reason"] == l.escalation_reason.value
    )
    reason_any = sum(
        1 for l, r in esc if escalated(r) and l.escalation_reason.value in (r.get("reasons") or [])
    )
    resolved = sum(r["outcome"] == "auto_resolved" for _, r in rows)
    errors = sum(1 for _, r in rows if r.get("error"))
    llm_calls = sum(r.get("llm_calls", 0) for _, r in rows)

    print(f"\n=== Results on {n} tickets ===")
    print(f"Category accuracy            {pct(cat_ok, n)}  ({cat_ok}/{n})")
    print(f"Escalation recall            {pct(caught, len(esc))}  ({caught}/{len(esc)} risky tickets caught)")
    print(f"Unsafe auto-resolves         {len(unsafe)}  (should escalate but did not)  <- the number that matters most")
    print(f"Over-escalation              {pct(len(over), len(non))}  ({len(over)}/{len(non)} safe tickets sent to a human)")
    print(f"Primary reason match         {pct(reason_ok, len(esc))}  ({reason_ok}/{len(esc)} escalations, strict: top reason only)")
    print(f"Reason found anywhere        {pct(reason_any, len(esc))}  ({reason_any}/{len(esc)} escalations, expected reason among all reasons)")
    print(f"Auto-resolve rate            {pct(resolved, n)}  (ceiling on this set: {pct(len(non), n)})")
    print(f"Pipeline errors              {errors}")
    print(f"LLM calls                    {llm_calls}")
    if errors:
        seen = Counter(str(r["error"])[:300] for _, r in rows if r.get("error"))
        print("\nErrors (most common first). If every ticket failed, run: python scripts/check_llm.py")
        for msg, k in seen.most_common(3):
            print(f"  x{k}  {msg}")

    cats = ("billing", "technical", "account", "other")
    print("\nPer-category accuracy:")
    for c in cats:
        sub = [(l, r) for l, r in rows if l.category.value == c]
        if sub:
            ok = sum(r["category"] == c for _, r in sub)
            print(f"  {c:10} {pct(ok, len(sub)):>5}  ({ok}/{len(sub)})")

    if unsafe:
        print("\nUNSAFE auto-resolves (fix these first):")
        for l, r in unsafe:
            print(f"  {l.id} [{l.escalation_reason.value}] {l.text[:80]}")
    if over:
        print("\nOver-escalations:")
        for l, r in over[:15]:
            print(f"  {l.id} reasons={r['reasons']} {l.text[:70]}")
    misrouted = [(l, r) for l, r in rows if l.category.value != r["category"]]
    if misrouted:
        print(f"\nMisrouted ({len(misrouted)}), first 15:")
        for l, r in misrouted[:15]:
            print(f"  {l.id} expected={l.category.value} got={r['category']}  {l.text[:60]}")
    wrong_reason = Counter(
        (l.escalation_reason.value, r["primary_reason"])
        for l, r in esc
        if escalated(r) and r["primary_reason"] != l.escalation_reason.value
    )
    if wrong_reason:
        print("\nReason mismatches (expected -> got):")
        for (exp, got), k in wrong_reason.most_common(10):
            print(f"  {exp} -> {got}  x{k}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["stub", "groq"], help="override LLM_PROVIDER")
    ap.add_argument("--model", help="override LLM_MODEL")
    ap.add_argument("--dataset", default=str(DATA),
                    help="labeled .jsonl to run (default: the 100-ticket dev set). "
                         "Results for other datasets are saved in separate files.")
    ap.add_argument("--limit", type=int, help="only run the first N tickets")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to sleep between tickets")
    ap.add_argument("--fresh", action="store_true", help="ignore and overwrite saved results")
    ap.add_argument("--verbose", action="store_true", help="print every ticket's decision")
    args = ap.parse_args()

    settings = get_settings()
    if args.provider:
        settings = replace(settings, llm_provider=args.provider)
    if args.model:
        settings = replace(settings, llm_model=args.model)

    llm = make_llm(settings)
    graph = build_graph(llm=llm, settings=settings)
    dataset = Path(args.dataset).resolve()
    labels = load_labels(dataset)
    if args.limit:
        labels = labels[: args.limit]

    tag = settings.llm_provider if settings.llm_provider == "stub" else f"{settings.llm_provider}_{settings.llm_model}"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "" if dataset == DATA.resolve() else f"__{dataset.stem}"
    out_path = RESULTS_DIR / f"{tag.replace('/', '-')}{suffix}.jsonl"
    if args.fresh and out_path.exists():
        out_path.unlink()

    results: dict[str, dict] = {}
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                results[r["id"]] = r
    todo = [l for l in labels if l.id not in results]
    print(f"Provider: {tag} | {len(labels)} tickets, {len(results)} already done, {len(todo)} to run")

    with out_path.open("a", encoding="utf-8") as f:
        for i, label in enumerate(todo, start=1):
            before = llm.calls
            state = run_ticket(graph, label.id, label.text)
            reasons = state.get("guardrail_reasons", [])
            r = {
                "id": label.id,
                "category": state.get("category"),
                "sentiment": state.get("sentiment"),
                "urgency": state.get("urgency"),
                "outcome": state.get("final_outcome"),
                "primary_reason": reasons[0] if reasons else None,
                "reasons": reasons,
                "error": state.get("error"),
                "llm_calls": llm.calls - before,
                "trace": state.get("trace", []),
            }
            results[label.id] = r
            f.write(json.dumps(r) + "\n")
            f.flush()
            if args.verbose:
                ok = "OK " if (r["outcome"] == "escalated") == label.should_escalate else "BAD"
                print(f"[{ok}] {label.id} {r['category']:9} -> {r['outcome']:13} {reasons[:2]}")
            elif i % 10 == 0:
                print(f"  ...{i}/{len(todo)}")
            if args.delay:
                time.sleep(args.delay)

    print_metrics(labels, results)


if __name__ == "__main__":
    main()
