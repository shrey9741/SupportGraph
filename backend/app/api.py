"""FastAPI app. `create_app` is a factory so tests can inject settings and a graph.

Endpoints
  POST /tickets                 submit a ticket (idempotent if ticket_id is given)
  GET  /tickets                 list tickets (filter by status)
  GET  /tickets/{id}            one ticket with outcome and review
  GET  /tickets/{id}/trace      the full audit trail for a ticket
  GET  /tickets/{id}/stream     live Server-Sent Events: one event per pipeline step
  POST /tickets/{id}/review     a human approves, edits or rejects an escalated ticket
  GET  /stats                   aggregates for the dashboard
  GET  /health                  open (also says whether login is required)
  POST /auth/login              email and password -> signed token
  GET  /auth/me                 the logged-in user
  POST /auth/change-password
  GET/POST /users, PATCH /users/{id}   admin only: manage reviewer accounts

Everything except /health and /auth/login needs `Authorization: Bearer <token>` unless
AUTH_REQUIRED=false (local experiments and most tests). Reviews are attributed to the
logged-in account, never to a name typed by the client.
"""
import json
import logging
import secrets
import time
import uuid
from typing import Any, Literal, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from . import auth, db
from .config import Settings, get_settings
from .graph import build_graph
from .service import process_ticket

Status = Literal["processing", "auto_resolved", "escalated", "failed"]
STREAM_TIMEOUT_S = 120
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
log = logging.getLogger("supportgraph.api")
LOCAL_USER = {"id": 0, "email": "local@localhost", "name": "Local user", "role": "admin", "active": 1}


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


class LoginRequest(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class UserCreate(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(max_length=200)
    role: Literal["admin", "reviewer"] = "reviewer"


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    role: Optional[Literal["admin", "reviewer"]] = None
    active: Optional[bool] = None
    password: Optional[str] = Field(default=None, max_length=200)  # admin password reset


def _public(user: dict[str, Any]) -> dict[str, Any]:
    return {k: user[k] for k in ("id", "email", "name", "role", "active", "created_at") if k in user}


class ReviewRequest(BaseModel):
    action: Literal["approve", "edit", "reject"]
    # Ignored when login is required: the reviewer is the logged-in account.
    reviewer: Optional[str] = Field(default=None, max_length=100)
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

    secret = settings.jwt_secret
    if settings.auth_required:
        if secret is None:
            secret = secrets.token_urlsafe(48)
            log.warning("JWT_SECRET is not set: using a random one, so everyone is logged out when the API restarts.")
        elif len(secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        with db.session(path) as conn:
            if db.count_users(conn) == 0:
                if settings.admin_email and settings.admin_password:
                    problem = auth.check_password_policy(settings.admin_password)
                    if problem:
                        raise ValueError(f"ADMIN_PASSWORD: {problem}")
                    db.create_user(conn, settings.admin_email, "Admin", auth.hash_password(settings.admin_password), "admin")
                    log.info("Created the first admin account for %s", settings.admin_email)
                else:
                    log.warning("There are no user accounts. Set ADMIN_EMAIL and ADMIN_PASSWORD to create the first admin.")
    email_throttle, ip_throttle = auth.LoginThrottle(limit=5), auth.LoginThrottle(limit=30)
    bearer = HTTPBearer(auto_error=False)

    def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> dict[str, Any]:
        if not settings.auth_required:
            return LOCAL_USER
        unauthorised = HTTPException(401, "not authenticated", headers={"WWW-Authenticate": "Bearer"})
        if creds is None:
            raise unauthorised
        user_id = auth.decode_token(creds.credentials, secret)
        if user_id is None:
            raise HTTPException(401, "invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
        with db.session(path) as conn:
            user = db.get_user(conn, user_id)
        if not user or not user["active"]:
            raise unauthorised
        return _public(user)

    def admin_user(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user["role"] != "admin":
            raise HTTPException(403, "admin access required")
        return user

    AUTH = [Depends(current_user)]

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
            "auth_required": settings.auth_required,
        }

    # ---------------------------------------------------------------- auth ----

    @app.post("/auth/login")
    def login(body: LoginRequest, request: Request):
        if not settings.auth_required:
            raise HTTPException(400, "authentication is disabled on this server")
        email, ip = body.email.strip().lower(), (request.client.host if request.client else "unknown")
        if email_throttle.blocked(email) or ip_throttle.blocked(ip):
            raise HTTPException(429, "too many failed attempts, try again in a few minutes")
        with db.session(path) as conn:
            user = db.get_user_by_email(conn, email)
        ok = bool(user and user["active"] and auth.verify_password(body.password, user["password_hash"]))
        if not user:
            auth.verify_against_dummy(body.password)
        if not ok:
            email_throttle.record_failure(email)
            ip_throttle.record_failure(ip)
            raise HTTPException(401, "incorrect email or password")
        email_throttle.reset(email)
        return {
            "access_token": auth.create_token(user["id"], secret, settings.token_ttl_hours),
            "token_type": "bearer",
            "expires_in": int(settings.token_ttl_hours * 3600),
            "user": _public(user),
        }

    @app.get("/auth/me")
    def me(user: dict = Depends(current_user)):
        return user

    @app.post("/auth/change-password")
    def change_password(body: PasswordChange, user: dict = Depends(current_user)):
        if not settings.auth_required:
            raise HTTPException(400, "authentication is disabled on this server")
        with db.session(path) as conn:
            full = db.get_user(conn, user["id"])
            if not auth.verify_password(body.current_password, full["password_hash"]):
                raise HTTPException(403, "current password is incorrect")
            problem = auth.check_password_policy(body.new_password)
            if problem:
                raise HTTPException(422, problem)
            db.update_user(conn, user["id"], password_hash=auth.hash_password(body.new_password))
        return {"ok": True}

    @app.get("/users")
    def users(_: dict = Depends(admin_user)):
        with db.session(path) as conn:
            return {"items": db.list_users(conn)}

    @app.post("/users", status_code=201)
    def add_user(body: UserCreate, _: dict = Depends(admin_user)):
        problem = auth.check_password_policy(body.password)
        if problem:
            raise HTTPException(422, problem)
        with db.session(path) as conn:
            if db.get_user_by_email(conn, body.email):
                raise HTTPException(409, "a user with that email already exists")
            uid = db.create_user(conn, body.email, body.name.strip(), auth.hash_password(body.password), body.role)
            return _public(db.get_user(conn, uid))

    @app.patch("/users/{user_id}")
    def edit_user(user_id: int, body: UserUpdate, admin: dict = Depends(admin_user)):
        with db.session(path) as conn:
            target = db.get_user(conn, user_id)
            if target is None:
                raise HTTPException(404, "user not found")
            removing_admin = target["role"] == "admin" and target["active"] and (
                body.active is False or (body.role is not None and body.role != "admin"))
            if removing_admin:
                if target["id"] == admin["id"]:
                    raise HTTPException(409, "you cannot deactivate or demote your own account")
                if db.count_active_admins(conn) <= 1:
                    raise HTTPException(409, "there must be at least one active admin")
            new_hash = None
            if body.password is not None:
                problem = auth.check_password_policy(body.password)
                if problem:
                    raise HTTPException(422, problem)
                new_hash = auth.hash_password(body.password)
            db.update_user(conn, user_id, name=body.name, role=body.role,
                           active=None if body.active is None else int(body.active), password_hash=new_hash)
            return _public(db.get_user(conn, user_id))

    @app.post("/tickets", status_code=202, dependencies=AUTH)
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

    @app.get("/tickets", dependencies=AUTH)
    def list_all(
        status: Optional[Status] = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        with db.session(path) as conn:
            items, total = db.list_tickets(conn, status, limit, offset)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.get("/tickets/{ticket_id}", dependencies=AUTH)
    def get_one(ticket_id: str):
        with db.session(path) as conn:
            t = db.get_ticket(conn, ticket_id)
        if t is None:
            raise HTTPException(404, "ticket not found")
        return t

    @app.get("/tickets/{ticket_id}/trace", dependencies=AUTH)
    def trace(ticket_id: str):
        with db.session(path) as conn:
            t = db.get_ticket(conn, ticket_id)
            if t is None:
                raise HTTPException(404, "ticket not found")
            events = db.get_events(conn, ticket_id)
        return {"ticket_id": ticket_id, "status": t["status"], "events": events}

    @app.get("/tickets/{ticket_id}/stream", dependencies=AUTH)
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
    def review(ticket_id: str, body: ReviewRequest, user: dict = Depends(current_user)):
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

            # With login required the reviewer is the account, never a client-supplied name.
            reviewer = user["name"] if settings.auth_required else (body.reviewer or user["name"])
            reviewer_id = user["id"] if settings.auth_required else None
            db.add_review(conn, ticket_id, body.action, reviewer, body.edited_reply, final, body.note, reviewer_id)
            db.add_event(conn, ticket_id, db.next_seq(conn, ticket_id), {
                "node": "human_review", "at": db.now(),
                "output": {"action": body.action, "reviewer": reviewer, "reviewer_email": user["email"],
                           "edited": body.action == "edit", "note": body.note},
            })
            return db.get_ticket(conn, ticket_id)

    @app.get("/stats", dependencies=AUTH)
    def get_stats():
        with db.session(path) as conn:
            return db.stats(conn)

    return app
