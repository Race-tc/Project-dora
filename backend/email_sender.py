"""
backend/email_sender.py — Send licence key emails via SMTP.
"""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = cfg.SMTP_FROM
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))

    if cfg.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(cfg.SMTP_HOST, cfg.SMTP_PORT) as server:
            server.login(cfg.SMTP_USER, cfg.SMTP_PASS)
            server.sendmail(cfg.SMTP_FROM, to_email, msg.as_string())
    else:
        with smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT) as server:
            server.starttls()
            server.login(cfg.SMTP_USER, cfg.SMTP_PASS)
            server.sendmail(cfg.SMTP_FROM, to_email, msg.as_string())
