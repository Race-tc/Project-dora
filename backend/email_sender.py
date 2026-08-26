"""
backend/email_sender.py — Send licence key emails via Resend's HTTP API.

Raw SMTP (ports 465/587) is blocked outbound on Railway's Free/Trial/Hobby
plans to prevent spam abuse, only unblocked on Pro — so this goes over
HTTPS instead, which isn't restricted.
"""
from __future__ import annotations

import httpx

from settings import cfg


def _send(to_email: str, subject: str, html: str) -> None:
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {cfg.RESEND_API_KEY}"},
        json={
            "from":    cfg.EMAIL_FROM,
            "to":      [to_email],
            "subject": subject,
            "html":    html,
        },
        timeout=30.0,
    )
    resp.raise_for_status()


def send_licence_email(to_email: str, licence_key: str) -> None:
    html = f"""
    <html><body style="font-family:Arial,sans-serif;background:#0a0a1a;color:#e0e0ff;padding:32px">
    <div style="max-width:520px;margin:auto;background:#12122a;border-radius:8px;padding:32px">
      <h1 style="color:#7c6fff;margin-top:0">DORA</h1>
      <p>Thank you for subscribing! Here is your licence key:</p>
      <div style="background:#1a1a3a;border:1px solid #7c6fff;border-radius:6px;
                  padding:16px;font-family:monospace;font-size:18px;
                  letter-spacing:2px;text-align:center;color:#a0ff9a;margin:24px 0">
        {licence_key}
      </div>
      <p style="color:#888">To activate:</p>
      <ol style="color:#aaa;line-height:1.8">
        <li>Open DORA</li>
        <li>Go to <strong style="color:#e0e0ff">Settings</strong></li>
        <li>Paste your licence key and click <strong style="color:#e0e0ff">Save</strong></li>
      </ol>
      <p style="color:#666;font-size:12px;margin-top:32px;border-top:1px solid #222;padding-top:16px">
        Your subscription renews monthly. Manage or cancel at any time via the
        customer portal link in your Stripe receipt email.
      </p>
    </div>
    </body></html>
    """
    _send(to_email, "Your DORA Licence Key", html)


def send_waitlist_confirmation_email(to_email: str) -> None:
    html = """
    <html><body style="font-family:Arial,sans-serif;background:#0a0a1a;color:#e0e0ff;padding:32px">
    <div style="max-width:520px;margin:auto;background:#12122a;border-radius:8px;padding:32px">
      <h1 style="color:#7c6fff;margin-top:0">DORA</h1>
      <p>You're on the waitlist. The free beta launches <strong style="color:#e0e0ff">16 September</strong> —
      we'll email your beta licence key the moment it's live.</p>
      <p style="color:#888;font-size:13px;margin-top:24px">No payment, no card required. Just watch this inbox.</p>
    </div>
    </body></html>
    """
    _send(to_email, "You're on the DORA beta waitlist", html)


def send_beta_key_email(to_email: str, licence_key: str, beta_end_date: str) -> None:
    html = f"""
    <html><body style="font-family:Arial,sans-serif;background:#0a0a1a;color:#e0e0ff;padding:32px">
    <div style="max-width:520px;margin:auto;background:#12122a;border-radius:8px;padding:32px">
      <h1 style="color:#7c6fff;margin-top:0">DORA</h1>
      <p>The beta is live! Here is your free licence key:</p>
      <div style="background:#1a1a3a;border:1px solid #7c6fff;border-radius:6px;
                  padding:16px;font-family:monospace;font-size:18px;
                  letter-spacing:2px;text-align:center;color:#a0ff9a;margin:24px 0">
        {licence_key}
      </div>
      <p style="color:#888">To activate:</p>
      <ol style="color:#aaa;line-height:1.8">
        <li>Download and install DORA</li>
        <li>Go to <strong style="color:#e0e0ff">Settings</strong></li>
        <li>Paste your licence key and click <strong style="color:#e0e0ff">Save</strong></li>
      </ol>
      <p style="color:#f59e0b;font-size:13px;margin-top:24px">
        This beta key stops working on {beta_end_date}. We'll email everyone
        before then about moving to a paid plan if you want to keep using DORA.
      </p>
    </div>
    </body></html>
    """
    _send(to_email, "Your DORA beta key is here", html)
