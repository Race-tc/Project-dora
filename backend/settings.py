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
    STRIPE_SETUP_PRICE_ID:  str   # price_xxx for the one-time £150 setup fee
    STRIPE_PRICE_ID:        str   # price_xxx for the £20/month recurring plan
    ADMIN_TOKEN:            str   # secret token for /admin endpoints
    BASE_URL:               str   # e.g. https://api.projectdora.com (backend)
    SITE_URL:               str   # e.g. https://projectdora.com (website)
    RESEND_API_KEY:         str   # from https://resend.com/api-keys
    EMAIL_FROM:             str   # "Name <address>" — must be a Resend-verified sender/domain
    LATEST_VERSION:         str   # desktop app version to advertise via GET /version
    DOWNLOAD_URL:           str   # where the desktop app's update dialog sends users
    RELEASE_NOTES:          str   # short blurb shown in the update dialog; optional
    BETA_END_DATE:          str   # ISO datetime — beta licences stop working after this


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
        STRIPE_SETUP_PRICE_ID = os.environ["STRIPE_SETUP_PRICE_ID"],
        STRIPE_PRICE_ID       = os.environ["STRIPE_PRICE_ID"],
        ADMIN_TOKEN           = os.environ["ADMIN_TOKEN"],
        BASE_URL              = os.environ.get("BASE_URL", "http://localhost:8000"),
        SITE_URL              = os.environ.get("SITE_URL", "https://projectdora.com"),
        RESEND_API_KEY        = os.environ["RESEND_API_KEY"],
        EMAIL_FROM            = os.environ.get("EMAIL_FROM", "DORA <onboarding@resend.dev>"),
        LATEST_VERSION        = os.environ.get("LATEST_VERSION", "2.0.0"),
        DOWNLOAD_URL          = os.environ.get(
            "DOWNLOAD_URL",
            os.environ.get("SITE_URL", "https://projectdora.com") + "/dora/#download",
        ),
        RELEASE_NOTES         = os.environ.get("RELEASE_NOTES", ""),
        BETA_END_DATE         = os.environ.get("BETA_END_DATE", "2026-10-28T23:59:59+00:00"),
    )


cfg = _load()
