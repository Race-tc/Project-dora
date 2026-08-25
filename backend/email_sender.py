"""
backend/email_sender.py — Send licence key emails via Resend's HTTP API.

Raw SMTP (ports 465/587) is blocked outbound on Railway's Free/Trial/Hobby
plans to prevent spam abuse, only unblocked on Pro — so this goes over
HTTPS instead, which isn't restricted.
"""
from __future__ import annotations

import httpx

from settings import cfg


def send_licence_email(to_email: str, licence_key: str) -> None:
    subject = "Your DORA Licence Key"

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
