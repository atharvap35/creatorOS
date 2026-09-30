import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_creator_os.db")

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app
from app.security import SESSION_COOKIE_NAME


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


def register(client, email="owner@example.com", password="supersecret", name="Alex Carter"):
    response = client.post(
        "/register",
        data={"name": name, "email": email, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert SESSION_COOKIE_NAME in client.cookies
    return response


def logout(client):
    client.post("/logout", follow_redirects=False)
    client.cookies.clear()


def test_root_redirects_to_login_for_guests(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_guest_is_redirected_from_dashboard(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_register_creates_workspace(client):
    register(client)

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Alex" in dashboard.text

    settings_page = client.get("/settings")
    assert settings_page.status_code == 200


def test_register_rejects_duplicate_email(client):
    register(client)
    logout(client)

    response = client.post(
        "/register",
        data={"name": "Someone Else", "email": "owner@example.com", "password": "supersecret"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "already exists" in response.text


def test_register_rejects_short_password(client):
    response = client.post(
        "/register",
        data={"name": "Alex", "email": "a@b.com", "password": "short"},
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_login_and_logout(client):
    register(client, email="login@example.com")
    logout(client)

    bad = client.post(
        "/login",
        data={"email": "login@example.com", "password": "wrongpassword"},
        follow_redirects=False,
    )
    assert bad.status_code == 401

    good = client.post(
        "/login",
        data={"email": "login@example.com", "password": "supersecret"},
        follow_redirects=False,
    )
    assert good.status_code == 303
    assert client.get("/dashboard").status_code == 200

    client.post("/logout", follow_redirects=False)
    assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_password_hashing_is_not_plaintext(client):
    from app.database import SessionLocal
    from app.models.user import User

    register(client, email="hash@example.com")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "hash@example.com").first()
        assert user.hashed_password != "supersecret"
        assert user.hashed_password.startswith("pbkdf2_sha256$")
    finally:
        db.close()


def test_workspaces_are_isolated(client):
    register(client, email="one@example.com", name="One")
    client.post("/content", data={"title": "First creator content", "platform": "youtube", "content_type": "video"})
    client.post("/tasks", data={"title": "First creator task"})

    logout(client)
    register(client, email="two@example.com", name="Two")

    assert "First creator content" not in client.get("/content").text
    assert "First creator task" not in client.get("/tasks").text

    client.post("/content", data={"title": "Second creator content", "platform": "tiktok", "content_type": "reel"})
    page = client.get("/content").text
    assert "Second creator content" in page
    assert "First creator content" not in page


def test_cannot_touch_another_users_records(client):
    from app.database import SessionLocal
    from app.models.task import Task

    register(client, email="victim@example.com")
    db = SessionLocal()
    try:
        task_id = db.query(Task).filter(Task.user_id == 1).first().id
    finally:
        db.close()

    logout(client)
    register(client, email="attacker@example.com")

    response = client.post(f"/tasks/{task_id}/delete", follow_redirects=False)
    assert response.status_code == 303

    db = SessionLocal()
    try:
        assert db.query(Task).filter(Task.id == task_id).first() is not None
    finally:
        db.close()


def test_crud_flows_for_each_area(client):
    register(client)

    assert client.post(
        "/content",
        data={"title": "New reel", "platform": "instagram", "content_type": "reel", "status": "idea"},
        follow_redirects=False,
    ).status_code == 303
    assert client.post("/tasks", data={"title": "New task"}, follow_redirects=False).status_code == 303
    assert client.post(
        "/deals",
        data={"brand_name": "Acme", "campaign_name": "Launch", "deal_value": "1000"},
        follow_redirects=False,
    ).status_code == 303
    assert client.post(
        "/revenue",
        data={"source": "affiliate", "amount": "250.50", "status": "pending"},
        follow_redirects=False,
    ).status_code == 303
    assert client.post("/ideas", data={"title": "New idea"}, follow_redirects=False).status_code == 303
    assert client.post(
        "/opportunities",
        data={"title": "New opportunity", "estimated_value": "500"},
        follow_redirects=False,
    ).status_code == 303

    for path, needle in [
        ("/content", "New reel"),
        ("/tasks", "New task"),
        ("/deals", "Acme"),
        ("/revenue", "affiliate"),
        ("/ideas", "New idea"),
        ("/opportunities", "New opportunity"),
    ]:
        assert needle in client.get(path).text


def test_status_updates_apply(client):
    register(client)
    tasks_page = client.get("/tasks")
    assert "Mark done" in tasks_page.text

    from app.database import SessionLocal
    from app.models.task import Task, TaskStatus

    db = SessionLocal()
    try:
        task_id = db.query(Task).filter(Task.user_id == 1).first().id
    finally:
        db.close()

    client.post(f"/tasks/{task_id}/complete", follow_redirects=False)
    db = SessionLocal()
    try:
        assert db.get(Task, task_id).status == TaskStatus.completed
    finally:
        db.close()


def test_invalid_enum_input_does_not_crash(client):
    register(client)
    response = client.post(
        "/content",
        data={"title": "Weird", "platform": "not-a-platform", "content_type": "not-a-type", "status": "nope"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_filters_apply(client):
    register(client, email="filter@example.com")
    client.post("/ideas", data={"title": "Alpha idea"})

    assert "Alpha idea" not in client.get("/ideas", params={"q": "zzz"}).text
    assert "Alpha idea" in client.get("/ideas", params={"q": "Alpha"}).text


def test_settings_profile_update(client):
    register(client)
    response = client.post(
        "/settings/profile",
        data={"name": "Renamed", "niche": "Design", "currency": "EUR", "timezone": "Europe/London"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Renamed" in client.get("/settings").text


def test_currency_preference_is_applied_everywhere(client):
    register(client, email="money@example.com")
    client.post(
        "/settings/profile",
        data={"name": "Money Tester", "currency": "INR", "timezone": "Asia/Kolkata"},
        follow_redirects=False,
    )

    import re

    for path in ("/dashboard", "/deals", "/revenue", "/opportunities"):
        page = client.get(path).text
        assert "₹" in page, f"{path} should render the account currency"
        assert not re.search(r"\$[0-9]", page), f"{path} still shows hardcoded dollars"


def test_currency_preference_is_per_account(client):
    register(client, email="usd@example.com", name="Dollar User")
    client.post(
        "/settings/profile",
        data={"name": "Dollar User", "currency": "USD"},
        follow_redirects=False,
    )
    assert "$" in client.get("/revenue").text

    logout(client)
    register(client, email="inr@example.com", name="Rupee User")
    client.post(
        "/settings/profile",
        data={"name": "Rupee User", "currency": "INR"},
        follow_redirects=False,
    )
    assert "₹" in client.get("/revenue").text

    logout(client)
    client.post("/login", data={"email": "usd@example.com", "password": "supersecret"}, follow_redirects=False)
    assert "₹" not in client.get("/revenue").text
