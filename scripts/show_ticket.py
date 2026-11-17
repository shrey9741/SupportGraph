"""Print what the pipeline did for specific tickets in a saved results file.

    python scripts/show_ticket.py data/results/groq_openai-gpt-oss-20b__tickets_heldout_v2.jsonl V041 V042
"""
import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    path, wanted = Path(sys.argv[1]), set(sys.argv[2:])
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["id"] not in wanted:
            continue
        nodes = [e["node"] for e in r.get("trace", [])]
        print(f'{r["id"]}: outcome={r["outcome"]} category={r["category"]}')
        print(f'   reasons (primary first): {r["reasons"]}')
        print(f'   nodes: {" > ".join(nodes)}')
        print(f'   quarantined: {"quarantine" in nodes}')


if __name__ == "__main__":
    main()
