"""Load sample tickets into a running API so the UI has something to show.

    python scripts/seed_demo.py              # first 30 tickets from the dev set
    python scripts/seed_demo.py --limit 60 --url http://127.0.0.1:8000

Safe to re-run: ticket ids are fixed, and the API is idempotent per id.
"""
import argparse
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--dataset", default=str(ROOT / "data" / "tickets_labeled.jsonl"))
    args = p.parse_args()

    rows = [json.loads(line) for line in Path(args.dataset).read_text(encoding="utf-8").splitlines() if line.strip()]
    counts: dict[str, int] = {}
    with httpx.Client(base_url=args.url, timeout=120) as client:
        for row in rows[: args.limit]:
            r = client.post("/tickets", params={"wait": "true"}, json={"ticket_id": row["id"], "text": row["text"]})
            r.raise_for_status()
            status = r.json()["status"]
            counts[status] = counts.get(status, 0) + 1
    print("Seeded:", counts)


if __name__ == "__main__":
    main()
