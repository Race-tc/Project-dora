"""Smoke tests for the routes real money/licences/customer data flow through.

Not exhaustive — these exist so a regression in licence issuance, licence
validation, or webhook signature checking fails CI instead of surfacing as a
support email after a real customer pays. Every test that would otherwise
send a real email (Resend) monkeypatches the sender instead.
"""
import hmac
import hashlib
import time

import pytest
from fastapi.testclient import TestClient

import main
from settings import cfg


@pytest.fixture
def client(monkeypatch):
    # These endpoints call `from email_sender import send_x` inside the
    # function body, so patching the attribute on the email_sender module
    # (rather than on main) is what actually takes effect at call time.
    import email_sender
    monkeypatch.setattr(email_sender, "send_licence_email", lambda *a, **k: None)
    monkeypatch.setattr(email_sender, "send_waitlist_confirmation_email", lambda *a, **k: None)
    monkeypatch.setattr(email_sender, "send_beta_key_email", lambda *a, **k: None)
    with TestClient(main.app) as c:
        yield c


def test_version(client):
    resp = client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["latest"] == cfg.LATEST_VERSION
    assert body["download_url"] == cfg.DOWNLOAD_URL


def test_validate_unknown_key_is_invalid(client):
    resp = client.get("/validate/DORA-does-not-exist")
    assert resp.status_code == 200
    assert resp.json() == {"valid": False}


def test_admin_issue_requires_admin_token(client):
    resp = client.post("/admin/issue", json={"email": "nope@example.com"})
    assert resp.status_code == 422  # missing required header entirely

    resp = client.post(
        "/admin/issue",
        json={"email": "nope@example.com"},
        headers={"X-Admin-Token": "wrong-token"},
    )
    assert resp.status_code == 403


def test_admin_issue_then_validate_round_trip(client):
    resp = client.post(
        "/admin/issue",
        json={"email": "pilot@example.com", "note": "smoke test"},
        headers={"X-Admin-Token": cfg.ADMIN_TOKEN},
    )
    assert resp.status_code == 200
    key = resp.json()["licence_key"]
    assert key.startswith("DORA-")

    resp = client.get(f"/validate/{key}")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"valid": True, "email": "pilot@example.com", "tier": "shop"}


def test_waitlist_join_is_idempotent(client):
    resp = client.post("/waitlist", json={"email": "waiter@example.com"})
    assert resp.status_code == 200

    # Re-joining must not error or create a duplicate row (deliberately
    # idempotent per _join_waitlist's own docstring).
    resp = client.post("/waitlist", json={"email": "waiter@example.com"})
    assert resp.status_code == 200

    resp = client.get(
        "/admin/waitlist", headers={"X-Admin-Token": cfg.ADMIN_TOKEN}
    )
    assert resp.status_code == 200
    matches = [row for row in resp.json() if row["email"] == "waiter@example.com"]
    assert len(matches) == 1


def test_webhook_rejects_bad_signature(client):
    resp = client.post(
        "/webhook",
        content=b'{"type": "checkout.session.completed"}',
        headers={"stripe-signature": "t=0,v1=not-a-real-signature", "content-type": "application/json"},
    )
    assert resp.status_code == 400


def test_webhook_accepts_correctly_signed_payload(client):
    payload = b'{"id": "evt_test", "type": "some.unhandled.event", "data": {"object": {}}}'
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.".encode() + payload
    signature = hmac.new(
        cfg.STRIPE_WEBHOOK_SECRET.encode(), signed_payload, hashlib.sha256
    ).hexdigest()
    resp = client.post(
        "/webhook",
        content=payload,
        headers={
            "stripe-signature": f"t={timestamp},v1={signature}",
            "content-type": "application/json",
        },
    )
    # An unhandled event type still returns 200 — Stripe retries on
    # non-2xx, and this backend deliberately only branches on the event
    # types it cares about.
    assert resp.status_code == 200
