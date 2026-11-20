"""Accounts, tokens and permissions. Login is required here (unlike most other API tests)."""
import time

import pytest
from fastapi.testclient import TestClient

from app import auth, db
from app.api import create_app
from app.config import Settings
from app.graph import build_graph
from app.stub_llm import StubLLM

SECRET = "x" * 40
ADMIN = ("boss@example.com", "AdminPass1")
LEGAL = "I was charged after cancelling three times. I'm talking to a lawyer."


@pytest.fixture
def settings(tmp_path):
    return Settings(
        llm_provider="stub", database_path=str(tmp_path / "auth.db"), auth_required=True,
        jwt_secret=SECRET, admin_email=ADMIN[0], admin_password=ADMIN[1],
    )


@pytest.fixture
def client(settings):
    graph = build_graph(llm=StubLLM(), settings=settings)
    return TestClient(create_app(settings=settings, graph=graph))


def login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def headers(client, email=ADMIN[0], password=ADMIN[1]):
    r = login(client, email, password)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_reviewer(client, email="asha@example.com", name="Asha Varma", password="Reviewer1x"):
    r = client.post("/users", headers=headers(client), json={"email": email, "name": name, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------ access control --

def test_health_and_login_are_open_everything_else_is_not(client):
    assert client.get("/health").json()["auth_required"] is True
    for method, path in [("get", "/tickets"), ("get", "/stats"), ("get", "/tickets/x"),
                         ("get", "/tickets/x/trace"), ("get", "/tickets/x/stream"),
                         ("get", "/auth/me"), ("get", "/users")]:
        assert getattr(client, method)(path).status_code == 401, path
    assert client.post("/tickets", json={"text": "hi"}).status_code == 401
    assert client.post("/tickets/x/review", json={"action": "reject"}).status_code == 401


def test_bad_tokens_are_rejected(client):
    assert client.get("/tickets", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    forged = auth.create_token(1, "y" * 40, 1)  # signed with a different secret
    assert client.get("/tickets", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_expired_token_is_rejected(client):
    expired = auth.create_token(1, SECRET, -1)
    r = client.get("/tickets", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_valid_token_works(client):
    h = headers(client)
    assert client.get("/tickets", headers=h).status_code == 200
    me = client.get("/auth/me", headers=h).json()
    assert me["email"] == ADMIN[0] and me["role"] == "admin" and "password_hash" not in me


# --------------------------------------------------------------------- login --

def test_wrong_password_and_unknown_user_look_the_same(client):
    a = login(client, ADMIN[0], "WrongPass1")
    b = login(client, "nobody@example.com", "WrongPass1")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_login_is_case_insensitive_on_email(client):
    assert login(client, ADMIN[0].upper(), ADMIN[1]).status_code == 200


def test_login_throttle_blocks_after_repeated_failures(client):
    for _ in range(5):
        assert login(client, ADMIN[0], "WrongPass1").status_code == 401
    assert login(client, ADMIN[0], "WrongPass1").status_code == 429
    assert login(client, ADMIN[0], ADMIN[1]).status_code == 429  # even the right password, until the window passes


def test_passwords_are_hashed_in_the_database(client, settings):
    with db.session(settings.database_path) as conn:
        stored = db.get_user_by_email(conn, ADMIN[0])["password_hash"]
    assert ADMIN[1] not in stored and stored.startswith("scrypt$")


# ------------------------------------------------------------ bootstrap admin --

def test_first_admin_is_created_from_settings_only_when_no_users_exist(settings):
    create_app(settings=settings, graph=build_graph(llm=StubLLM(), settings=settings))
    other = Settings(**{**settings.__dict__, "admin_email": "second@example.com"})
    create_app(settings=other, graph=build_graph(llm=StubLLM(), settings=other))
    with db.session(settings.database_path) as conn:
        assert [u["email"] for u in db.list_users(conn)] == [ADMIN[0]]


def test_weak_bootstrap_password_is_refused(tmp_path):
    s = Settings(llm_provider="stub", database_path=str(tmp_path / "w.db"), auth_required=True,
                 jwt_secret=SECRET, admin_email="a@example.com", admin_password="short")
    with pytest.raises(ValueError):
        create_app(settings=s, graph=build_graph(llm=StubLLM(), settings=s))


def test_short_jwt_secret_is_refused(tmp_path):
    s = Settings(llm_provider="stub", database_path=str(tmp_path / "j.db"), auth_required=True, jwt_secret="short")
    with pytest.raises(ValueError):
        create_app(settings=s, graph=build_graph(llm=StubLLM(), settings=s))


# --------------------------------------------------------------- user admin --

def test_only_admins_can_manage_users(client):
    make_reviewer(client)
    rh = headers(client, "asha@example.com", "Reviewer1x")
    assert client.get("/users", headers=rh).status_code == 403
    assert client.post("/users", headers=rh, json={
        "email": "x@example.com", "name": "X", "password": "Passw0rdx"}).status_code == 403


def test_user_creation_rules(client):
    h = headers(client)
    make_reviewer(client)
    dup = client.post("/users", headers=h, json={"email": "ASHA@example.com", "name": "A", "password": "Reviewer1x"})
    assert dup.status_code == 409
    weak = client.post("/users", headers=h, json={"email": "w@example.com", "name": "W", "password": "alllowercase"})
    assert weak.status_code == 422
    bad = client.post("/users", headers=h, json={"email": "not-an-email", "name": "W", "password": "Reviewer1x"})
    assert bad.status_code == 422
    listing = client.get("/users", headers=h).json()["items"]
    assert len(listing) == 2 and all("password_hash" not in u for u in listing)


def test_deactivated_user_is_locked_out_immediately(client):
    u = make_reviewer(client)
    rh = headers(client, "asha@example.com", "Reviewer1x")
    assert client.get("/tickets", headers=rh).status_code == 200
    r = client.patch(f"/users/{u['id']}", headers=headers(client), json={"active": False})
    assert r.status_code == 200
    assert client.get("/tickets", headers=rh).status_code == 401  # the old token stops working
    assert login(client, "asha@example.com", "Reviewer1x").status_code == 401


def test_admin_cannot_remove_the_last_admin_or_themselves(client):
    h = headers(client)
    me = client.get("/auth/me", headers=h).json()
    assert client.patch(f"/users/{me['id']}", headers=h, json={"active": False}).status_code == 409
    assert client.patch(f"/users/{me['id']}", headers=h, json={"role": "reviewer"}).status_code == 409


def test_admin_can_reset_a_password(client):
    u = make_reviewer(client)
    client.patch(f"/users/{u['id']}", headers=headers(client), json={"password": "NewPassw0rd"})
    assert login(client, "asha@example.com", "Reviewer1x").status_code == 401
    assert login(client, "asha@example.com", "NewPassw0rd").status_code == 200


def test_change_own_password(client):
    make_reviewer(client)
    rh = headers(client, "asha@example.com", "Reviewer1x")
    bad = client.post("/auth/change-password", headers=rh, json={"current_password": "nope", "new_password": "Another1xx"})
    assert bad.status_code == 403
    weak = client.post("/auth/change-password", headers=rh, json={"current_password": "Reviewer1x", "new_password": "weak"})
    assert weak.status_code == 422
    ok = client.post("/auth/change-password", headers=rh, json={"current_password": "Reviewer1x", "new_password": "Another1xx"})
    assert ok.status_code == 200
    assert login(client, "asha@example.com", "Another1xx").status_code == 200


# ------------------------------------------------------- review attribution ---

def test_review_is_attributed_to_the_account_not_the_request_body(client):
    make_reviewer(client)
    rh = headers(client, "asha@example.com", "Reviewer1x")
    t = client.post("/tickets", headers=rh, params={"wait": True}, json={"text": LEGAL}).json()
    assert t["status"] == "escalated"
    r = client.post(f"/tickets/{t['id']}/review", headers=rh, json={"action": "approve", "reviewer": "Someone Else"})
    assert r.status_code == 200
    review = r.json()["review"]
    assert review["reviewer"] == "Asha Varma" and review["reviewer_id"] is not None
    events = client.get(f"/tickets/{t['id']}/trace", headers=rh).json()["events"]
    human = [e for e in events if e["node"] == "human_review"][0]["output"]
    assert human["reviewer"] == "Asha Varma" and human["reviewer_email"] == "asha@example.com"


def test_stream_requires_a_token_and_works_with_one(client):
    h = headers(client)
    t = client.post("/tickets", headers=h, params={"wait": True}, json={"text": LEGAL}).json()
    assert client.get(f"/tickets/{t['id']}/stream").status_code == 401
    r = client.get(f"/tickets/{t['id']}/stream", headers=h)
    assert r.status_code == 200 and "event: done" in r.text


# ------------------------------------------------------------ auth disabled ---

def test_login_disabled_server_lets_requests_through(tmp_path):
    s = Settings(llm_provider="stub", database_path=str(tmp_path / "off.db"), auth_required=False)
    c = TestClient(create_app(settings=s, graph=build_graph(llm=StubLLM(), settings=s)))
    assert c.get("/health").json()["auth_required"] is False
    assert c.get("/tickets").status_code == 200
    assert c.post("/auth/login", json={"email": "a@b.co", "password": "x"}).status_code == 400
