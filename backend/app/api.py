"""FastAPI app. `create_app` is a factory so tests can inject settings and a graph.

Endpoints
  POST /tickets                 submit a ticket (idempotent if ticket_id is given)
  GET  /tickets                 list tickets (filter by status)
  GET  /tickets/{id}            one ticket with outcome and review
  GET  /tickets/{id}/trace      the full audit trail for a ticket
  GET  /tickets/{id}/stream     live Server-Sent Events: one event per pipeline step
  POST /tickets/{id}/review     a human approves, edits or rejects an escalated ticket
  GET  /stats                   aggregates for the dashboard
  GET  /health

No authentication: this is a local portfolio project. Do not expose it publicly.
"""
import json
import time
import uuid
from typing import Any, Literal, Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from . import db
from .config import Settings, get_settings
from .graph import build_graph
from .service import process_ticket

Status = Literal["processing", "auto_resolved", "escalated", "failed"]
STREAM_TIMEOUT_S = 120


class TicketCreate(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    # Optional client-supplied id doubles as an idempotency key.
    ticket_id: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be blank")
        return v


class ReviewRequest(BaseModel):
    action: Literal["approve", "edit", "reject"]
    reviewer: str = Field(min_length=1, max_length=100)
    edited_reply: Optional[str] = Field(default=None, max_length=5000)
    note: Optional[str] = Field(default=None, max_length=1000)


def _sse(event: str, data: dict[str, Any], event_id: Optional[int] = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data)}\n\n"


def create_app(settings: Optional[Settings] = None, graph=None) -> FastAPI:
    settings = settings or get_settings()
    path = settings.database_path
    db.init_db(path)
    graph = graph or build_graph(settings=settings)

    app = FastAPI(title="SupportGraph API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "provider": settings.llm_provider,
            "model": settings.llm_model if settings.llm_provider != "stub" else "keyword-baseline",
        }

    @app.post("/tickets", status_code=202)
    def submit(body: TicketCreate, background: BackgroundTasks, response: Response, wait: bool = False):
        """Submit a ticket. Returns 202 with status 'processing' and runs the pipeline in
        the background (follow it on /stream). With ?wait=true it runs inline and returns 201."""
        ticket_id = body.ticket_id or uuid.uuid4().hex[:12]
        with db.session(path) as conn:
            created = db.create_ticket(conn, ticket_id, body.text)
            ticket = db.get_ticket(conn, ticket_id)
        if not created:
            if ticket["text"] != body.text:
                raise HTTPException(409, f"ticket_id {ticket_id!r} already exists with different text")
            response.status_code = 200
            return {**ticket, "already_existed": True}

        if wait:
            process_ticket(graph, path, ticket_id, body.text)
            response.status_code = 201
            with db.session(path) as conn:
                return db.get_ticket(conn, ticket_id)
        background.add_task(process_ticket, graph, path, ticket_id, body.text)
        return {**ticket, "stream_url": f"/tickets/{ticket_id}/stream", "trace_url": f"/tickets/{ticket_id}/trace"}

    @app.get("/tickets")
    def list_all(
        status: Optional[Status] = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        with db.session(path) as conn:
            items, total = db.list_tickets(conn, status, limit, offset)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.get("/tickets/{ticket_id}")
    def get_one(ticket_id: str):
        with db.session(path) as conn:
            t = db.get_ticket(conn, ticket_id)
        if t is None:
            raise HTTPException(404, "ticket not found")
        return t

    @app.get("/tickets/{ticket_id}/trace")
    def trace(ticket_id: str):
        with db.session(path) as conn:
            t = db.get_ticket(conn, ticket_id)
            if t is None:
                raise HTTPException(404, "ticket not found")
            events = db.get_events(conn, ticket_id)
        return {"ticket_id": ticket_id, "status": t["status"], "events": events}

    @app.get("/tickets/{ticket_id}/stream")
    def stream(ticket_id: str, after: int = 0, last_event_id: Optional[str] = Header(default=None)):
        """Server-Sent Events that tail the audit log: one `trace` event per pipeline step,
        then a final `done` event. Reconnecting with Last-Event-ID resumes where it left off."""
        with db.session(path) as conn:
            if db.get_ticket(conn, ticket_id) is None:
                raise HTTPException(404, "ticket not found")
        last = int(last_event_id) if last_event_id and last_event_id.isdigit() else after

        def gen():
            nonlocal last
            deadline = time.monotonic() + STREAM_TIMEOUT_S
            while True:
                # Read status BEFORE events: if the ticket was already finished, every
                # event was written before that, so this read cannot miss any.
                with db.session(path) as conn:
                    t = db.get_ticket(conn, ticket_id)
                    events = db.get_events(conn, ticket_id, last)
                for ev in events:
                    last = ev["seq"]
                    yield _sse("trace", ev, event_id=ev["seq"])
                if t["status"] != "processing":
                    yield _sse("done", {
                        "ticket_id": ticket_id, "status": t["status"],
                        "primary_reason": t["primary_reason"], "category": t["category"],
                    })
                    return
                if time.monotonic() > deadline:
                    yield _sse("timeout", {"ticket_id": ticket_id})
                    return
                time.sleep(0.2)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/tickets/{ticket_id}/review")
    def review(ticket_id: str, body: ReviewRequest):
        """Human-in-the-loop: approve the drafted reply, edit it, or reject. Logged to the audit trail."""
        with db.session(path) as conn:
            t = db.get_ticket(conn, ticket_id)
            if t is None:
                raise HTTPException(404, "ticket not found")
            if t["status"] not in ("escalated", "failed"):
                raise HTTPException(409, f"only escalated or failed tickets can be reviewed (status is {t['status']})")
            if t["review"]:
                raise HTTPException(409, "ticket has already been reviewed")

            if body.action == "approve":
                if not t["draft_reply"]:
                    raise HTTPException(422, "there is no drafted reply to approve; use edit or reject")
                final = t["draft_reply"]
            elif body.action == "edit":
                if not body.edited_reply or not body.edited_reply.strip():
                    raise HTTPException(422, "edited_reply is required for action 'edit'")
                final = body.edited_reply
            else:
                final = None

            db.add_review(conn, ticket_id, body.action, body.reviewer, body.edited_reply, final, body.note)
            db.add_event(conn, ticket_id, db.next_seq(conn, ticket_id), {
                "node": "human_review", "at": db.now(),
                "output": {"action": body.action, "reviewer": body.reviewer,
                           "edited": body.action == "edit", "note": body.note},
            })
            return db.get_ticket(conn, ticket_id)

    @app.get("/stats")
    def get_stats():
        with db.session(path) as conn:
            return db.stats(conn)

    return app
