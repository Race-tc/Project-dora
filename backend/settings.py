"""
backend/settings.py — Load backend environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


@dataclass(frozen=True)
class BackendConfig:
    ANTHROPIC_API_KEY:      str
    OPENAI_API_KEY:         str   # voice STT — server-held, never sent to clients
    OPENAI_TRANSCRIBE_MODEL: str  # e.g. gpt-transcribe
    ELEVENLABS_API_KEY:     str   # voice TTS — server-held, never sent to clients
    ELEVENLABS_VOICE_ID:    str   # default voice for /voice/synthesize
    ELEVENLABS_MODEL_ID:    str   # e.g. eleven_multilingual_v2
    STRIPE_SECRET_KEY:      str
    STRIPE_WEBHOOK_SECRET:  str
    STRIPE_PRICE_ID:        str   # price_xxx for the £30/month plan
    ADMIN_TOKEN:            str   # secret token for /admin endpoints
    BASE_URL:               str   # e.g. https://api.projectdora.com (backend)
    SITE_URL:               str   # e.g. https://projectdora.com (website)
    SMTP_HOST:              str
    SMTP_PORT:              int
    SMTP_USER:              str
    SMTP_PASS:              str
    SMTP_FROM:              str


def _load() -> BackendConfig:
    return BackendConfig(
        ANTHROPIC_API_KEY     = os.environ["ANTHROPIC_API_KEY"],
        OPENAI_API_KEY        = os.environ.get("OPENAI_API_KEY", ""),
        OPENAI_TRANSCRIBE_MODEL = os.environ.get("OPENAI_TRANSCRIBE_MODEL", "gpt-transcribe"),
        ELEVENLABS_API_KEY    = os.environ.get("ELEVENLABS_API_KEY", ""),
        ELEVENLABS_VOICE_ID   = os.environ.get("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"),
        ELEVENLABS_MODEL_ID   = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
        STRIPE_SECRET_KEY     = os.environ["STRIPE_SECRET_KEY"],
        STRIPE_WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"],
        STRIPE_PRICE_ID       = os.environ["STRIPE_PRICE_ID"],
        ADMIN_TOKEN           = os.environ["ADMIN_TOKEN"],
        BASE_URL              = os.environ.get("BASE_URL", "http://localhost:8000"),
        SITE_URL              = os.environ.get("SITE_URL", "https://projectdora.com"),
        SMTP_HOST             = os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        SMTP_PORT             = int(os.environ.get("SMTP_PORT", "465")),
        SMTP_USER             = os.environ["SMTP_USER"],
        SMTP_PASS             = os.environ["SMTP_PASS"],
        SMTP_FROM             = os.environ.get("SMTP_FROM", os.environ["SMTP_USER"]),
    )


cfg = _load()
