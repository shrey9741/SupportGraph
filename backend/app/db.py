"""SQLite persistence: tickets, the audit log (events), and human reviews.

Plain sqlite3, no ORM. Every node event is written as the pipeline runs, so the
`events` table is the audit log: it answers "why did the system do that?" later,
and the live stream endpoint simply tails it.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  status TEXT NOT NULL,              -- processing | auto_resolved | escalated | failed
  category TEXT,
  sentiment TEXT,
  urgency TEXT,
  primary_reason TEXT,
  reasons TEXT NOT NULL DEFAULT '[]',
  draft_reply TEXT,
  final_reply TEXT,
  escalation_packet TEXT,
  error TEXT,
  review_action TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id TEXT NOT NULL REFERENCES tickets(id),
  seq INTEGER NOT NULL,
  node TEXT NOT NULL,
  at TEXT NOT NULL,
  output TEXT NOT NULL,
  UNIQUE(ticket_id, seq)
);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id TEXT NOT NULL UNIQUE REFERENCES tickets(id),
  action TEXT NOT NULL,              -- approve | edit | reject
  edited_reply TEXT,
  final_reply TEXT,
  reviewer TEXT NOT NULL,
  note TEXT,
  at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_created ON tickets(created_at);
"""

JSON_FIELDS = ("reasons", "escalation_packet")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # readers (the live stream) don't block the writer
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def session(path: str) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: str) -> None:
    with session(path) as conn:
        conn.executescript(SCHEMA)


def _ticket(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for f in JSON_FIELDS:
        d[f] = json.loads(d[f]) if d.get(f) else ([] if f == "reasons" else None)
    return d


# ---------------------------------------------------------------- tickets ----

def create_ticket(conn: sqlite3.Connection, ticket_id: str, text: str) -> bool:
    """Insert a new ticket. Returns False if the id already exists (idempotent submit)."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO tickets (id, text, status, created_at) VALUES (?, ?, 'processing', ?)",
        (ticket_id, text, now()),
    )
    return cur.rowcount == 1


def get_ticket(conn: sqlite3.Connection, ticket_id: str) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if row is None:
        return None
    t = _ticket(row)
    review = conn.execute("SELECT * FROM reviews WHERE ticket_id = ?", (ticket_id,)).fetchone()
    t["review"] = dict(review) if review else None
    return t


def list_tickets(conn: sqlite3.Connection, status: Optional[str], limit: int, offset: int) -> tuple[list[dict], int]:
    where, args = ("WHERE status = ?", [status]) if status else ("", [])
    total = conn.execute(f"SELECT COUNT(*) FROM tickets {where}", args).fetchone()[0]
    rows = conn.execute(
        f"""SELECT id, text, status, category, sentiment, urgency, primary_reason,
                   review_action, created_at, completed_at
            FROM tickets {where} ORDER BY created_at DESC, id LIMIT ? OFFSET ?""",
        [*args, limit, offset],
    ).fetchall()
    return [dict(r) for r in rows], total


def complete_ticket(conn: sqlite3.Connection, ticket_id: str, status: str, fields: dict[str, Any]) -> None:
    reasons = fields.get("guardrail_reasons") or []
    conn.execute(
        """UPDATE tickets SET status = ?, category = ?, sentiment = ?, urgency = ?,
               primary_reason = ?, reasons = ?, draft_reply = ?, final_reply = ?,
               escalation_packet = ?, error = ?, completed_at = ? WHERE id = ?""",
        (
            status, fields.get("category"), fields.get("sentiment"), fields.get("urgency"),
            reasons[0] if reasons else None, json.dumps(reasons),
            fields.get("draft_reply"), fields.get("final_reply"),
            json.dumps(fields["escalation_packet"]) if fields.get("escalation_packet") else None,
            fields.get("error"), now(), ticket_id,
        ),
    )


def fail_ticket(conn: sqlite3.Connection, ticket_id: str, error: str) -> None:
    conn.execute(
        "UPDATE tickets SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
        (error, now(), ticket_id),
    )


# ----------------------------------------------------------------- events ----

def add_event(conn: sqlite3.Connection, ticket_id: str, seq: int, event: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO events (ticket_id, seq, node, at, output) VALUES (?, ?, ?, ?, ?)",
        (ticket_id, seq, event["node"], event["at"], json.dumps(event.get("output", {}))),
    )


def next_seq(conn: sqlite3.Connection, ticket_id: str) -> int:
    return conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE ticket_id = ?", (ticket_id,)).fetchone()[0]


def get_events(conn: sqlite3.Connection, ticket_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT seq, node, at, output FROM events WHERE ticket_id = ? AND seq > ? ORDER BY seq",
        (ticket_id, after_seq),
    ).fetchall()
    return [{**dict(r), "output": json.loads(r["output"])} for r in rows]


# ---------------------------------------------------------------- reviews ----

def add_review(
    conn: sqlite3.Connection, ticket_id: str, action: str, reviewer: str,
    edited_reply: Optional[str], final_reply: Optional[str], note: Optional[str],
) -> None:
    conn.execute(
        """INSERT INTO reviews (ticket_id, action, edited_reply, final_reply, reviewer, note, at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (ticket_id, action, edited_reply, final_reply, reviewer, note, now()),
    )
    conn.execute("UPDATE tickets SET review_action = ? WHERE id = ?", (action, ticket_id))


# ------------------------------------------------------------------ stats ----

def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    by_status = {r["status"]: r["n"] for r in conn.execute("SELECT status, COUNT(*) AS n FROM tickets GROUP BY status")}
    completed = sum(by_status.get(s, 0) for s in ("auto_resolved", "escalated", "failed"))
    by_category = [
        dict(r) for r in conn.execute(
            """SELECT COALESCE(category, 'unknown') AS category, COUNT(*) AS total,
                      SUM(status = 'auto_resolved') AS auto_resolved,
                      SUM(status = 'escalated') AS escalated
               FROM tickets WHERE status != 'processing' GROUP BY 1 ORDER BY total DESC"""
        )
    ]
    reasons = [
        dict(r) for r in conn.execute(
            """SELECT primary_reason AS reason, COUNT(*) AS count FROM tickets
               WHERE status = 'escalated' AND primary_reason IS NOT NULL
               GROUP BY primary_reason ORDER BY count DESC, reason"""
        )
    ]
    reviews = {r["action"]: r["n"] for r in conn.execute("SELECT action, COUNT(*) AS n FROM reviews GROUP BY action")}
    avg = conn.execute(
        """SELECT AVG((julianday(completed_at) - julianday(created_at)) * 86400.0)
           FROM tickets WHERE completed_at IS NOT NULL"""
    ).fetchone()[0]
    return {
        "total": sum(by_status.values()),
        "processing": by_status.get("processing", 0),
        "auto_resolved": by_status.get("auto_resolved", 0),
        "escalated": by_status.get("escalated", 0),
        "failed": by_status.get("failed", 0),
        "auto_resolve_rate": round(by_status.get("auto_resolved", 0) / completed, 4) if completed else None,
        "by_category": by_category,
        "top_escalation_reasons": reasons,
        "reviews": {a: reviews.get(a, 0) for a in ("approve", "edit", "reject")},
        "avg_processing_seconds": round(avg, 3) if avg is not None else None,
    }
