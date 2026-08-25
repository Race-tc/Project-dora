"""
backend/main.py — DORA subscription backend.

Routes:
  POST /checkout          Create a Stripe Checkout session (garage signs up)
  POST /webhook           Stripe webhook (subscription events)
  POST /ai/analyse        Proxy AI analysis call (requires licence key)
  POST /ai/ask            Proxy a one-off prompt->text AI call (requires licence key)
  POST /ai/name-maps      Proxy AI map-naming call (requires licence key)
  POST /ai/explain-map    Proxy AI map-explainer call (requires licence key)
  POST /ai/chat           Proxy Dora's tool-using chat call (requires licence key)
  POST /voice/transcribe  Proxy speech-to-text via OpenAI (requires licence key)
  POST /voice/synthesize  Proxy text-to-speech via ElevenLabs (requires licence key)
  GET  /validate/{key}    Check if a licence key is active
  GET  /portal/{key}      Generate a Stripe customer portal link
  GET  /admin/licences    List all licences (requires admin token)
  POST /admin/issue       Manually issue a licence (requires admin token)
"""
from __future__ import annotations

import hmac

import stripe
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, EmailStr, field_validator

import database as db
from settings import cfg

# Applied to every request via the middleware below. Generous for the
# JSON bodies this app actually sends (log summaries, map/ROM context,
# chat history) while still bounding how much an arbitrary licence-key
# holder can force this server to buffer/forward per request. Multipart
# file uploads (/voice/transcribe) have their own, separate 25MB cap.
_MAX_REQUEST_BYTES = 5 * 1024 * 1024

# Models callers may request via a request-body `model` field. Keeps a
# licensed caller from requesting an arbitrary/expensive model string.
_ALLOWED_MODELS = {"claude-opus-5", "claude-sonnet-5"}


def _validate_model(v: str) -> str:
    if v not in _ALLOWED_MODELS:
        raise ValueError(f"model must be one of {sorted(_ALLOWED_MODELS)}")
    return v


def _cached_system(prompt: str) -> list[dict]:
    """Wrap a system prompt in block form with a cache breakpoint. These
    prompts are byte-identical across every licensed customer's call to a
    given route, so the cache write from the first request serves every
    other customer's request within the TTL — this is the single highest-
    value cache site in the app."""
    return [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]

stripe.api_key = cfg.STRIPE_SECRET_KEY

app = FastAPI(title="DORA Backend", version="1.0")

app.add_middleware(
    CORSMiddleware,
    # Only the marketing site's browser-side JS (website/app.js) makes
    # cross-origin calls into this backend (the desktop app and any
    # server-to-server calls aren't subject to CORS at all — it's a
    # browser-only mechanism), so this only needs to cover that origin.
    # Add a www. variant here too if the site is ever served from one.
    allow_origins=[cfg.SITE_URL],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _limit_request_size(request: Request, call_next):
    # /voice/transcribe has its own, larger 25MB cap for audio uploads —
    # everything else is JSON and has no business being anywhere near
    # that size. This only catches requests with an honest Content-Length
    # header (a fast pre-buffering check, same approach the voice endpoint
    # already uses); it doesn't defend chunked-encoding bodies with none.
    if request.url.path != "/voice/transcribe":
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_REQUEST_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})
    return await call_next(request)


db.init_db()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _require_admin(x_admin_token: str = Header(...)):
    if not hmac.compare_digest(x_admin_token, cfg.ADMIN_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid admin token")


def _require_licence(x_licence_key: str = Header(...)) -> db.sqlite3.Row:
    row = db.get_licence(x_licence_key)
    if not row:
        raise HTTPException(status_code=401, detail="Invalid licence key")
    if row["status"] != "active":
        raise HTTPException(
            status_code=402,
            detail=f"Licence is {row['status']}. "
                   "Renew your subscription at projectdora.com/billing",
        )
    return row


# ── Stripe Checkout ───────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    email: EmailStr


@app.post("/checkout")
async def create_checkout(body: CheckoutRequest):
    """Return a Stripe Checkout URL. Garage visits it to subscribe.

    Charges a one-time setup fee alongside the recurring subscription in a
    single Checkout session — Stripe supports mixing a one-time price into
    a mode="subscription" session; the one-time price is billed once on
    the first invoice and never recurs."""
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            customer_email=body.email,
            line_items=[
                {"price": cfg.STRIPE_SETUP_PRICE_ID, "quantity": 1},
                {"price": cfg.STRIPE_PRICE_ID, "quantity": 1},
            ],
            success_url=f"{cfg.SITE_URL}/success.html?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{cfg.SITE_URL}/cancelled.html",
            metadata={"email": body.email},
        )
    except stripe.error.StripeError as exc:
        raise HTTPException(
            status_code=502, detail=f"Stripe checkout error: {exc.user_message or str(exc)}"
        ) from exc
    return {"checkout_url": session.url}


# ── Stripe Webhook ────────────────────────────────────────────────────────────

@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload   = await request.body()
    sig       = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, cfg.STRIPE_WEBHOOK_SECRET
        )
    except (stripe.error.SignatureVerificationError, ValueError):
        # construct_event raises SignatureVerificationError for a bad
        # signature but a plain ValueError for a malformed/non-JSON
        # payload — both mean "reject this request", not "crash it".
        raise HTTPException(status_code=400, detail="Invalid signature or payload")

    etype = event["type"]
    # This Stripe SDK version returns a typed object (e.g. stripe.checkout.Session)
    # here, not a plain dict — .get() raises AttributeError on it. Convert once
    # up front so every .get()/[] access below behaves like ordinary dict access.
    data  = event["data"]["object"].to_dict()

    if etype == "checkout.session.completed":
        sub_id = data.get("subscription")
        if sub_id and db.get_licence_by_subscription_id(sub_id):
            # Stripe retries webhook delivery on any non-2xx response or
            # timeout — without this check a retried event mints a second
            # licence and sends a second "your licence key" email for the
            # same subscription.
            return {"ok": True}

        # New subscriber — create licence and email it
        email    = data.get("customer_email") or (data.get("metadata") or {}).get("email", "")
        cust_id  = data.get("customer")
        key      = db.create_licence(
            email=email,
            stripe_customer_id=cust_id,
            stripe_subscription_id=sub_id,
        )
        try:
            from email_sender import send_licence_email
            send_licence_email(email, key)
        except Exception as exc:
            # Log but don't fail the webhook — key is in the DB
            print(f"Email failed for {email}: {exc}")

    elif etype in ("customer.subscription.deleted",
                   "customer.subscription.paused"):
        if not db.set_status(data["id"], "cancelled"):
            # Stripe doesn't guarantee webhook delivery order — this can
            # legitimately arrive before the checkout.session.completed
            # that creates the licence row, in which case the status
            # change silently no-ops with nothing left to retry it. Not
            # auto-fixable here without a reconciliation job; at least
            # make it observable instead of vanishing outright.
            print(f"[webhook] set_status(cancelled) matched no licence for subscription {data['id']}")

    elif etype == "customer.subscription.updated":
        stripe_status = data.get("status", "active")
        dora_status   = "active" if stripe_status == "active" else "suspended"
        if not db.set_status(data["id"], dora_status):
            print(f"[webhook] set_status({dora_status}) matched no licence for subscription {data['id']}")

    elif etype == "invoice.payment_failed":
        sub_id = data.get("subscription")
        if sub_id and not db.set_status(sub_id, "suspended"):
            print(f"[webhook] set_status(suspended) matched no licence for subscription {sub_id}")

    return {"ok": True}


# ── Licence validation ────────────────────────────────────────────────────────

@app.get("/validate/{key}")
async def validate_licence(key: str):
    row = db.get_licence(key)
    if not row or row["status"] != "active":
        return {"valid": False}
    return {"valid": True, "email": row["email"]}


# ── Customer portal ───────────────────────────────────────────────────────────

@app.get("/portal/{key}")
async def customer_portal(key: str):
    row = db.get_licence(key)
    if not row or not row["stripe_customer_id"]:
        raise HTTPException(status_code=404, detail="Licence not found")
    try:
        session = stripe.billing_portal.Session.create(
            customer=row["stripe_customer_id"],
            return_url=f"{cfg.BASE_URL}/",
        )
    except stripe.error.StripeError as exc:
        raise HTTPException(
            status_code=502, detail=f"Stripe portal error: {exc.user_message or str(exc)}"
        ) from exc
    return {"portal_url": session.url}


# ── AI proxy ──────────────────────────────────────────────────────────────────

class AnalyseRequest(BaseModel):
    log_summary:  dict
    rom_context:  dict = {}
    map_context:  dict = {}
    model:        str  = "claude-opus-5"

    _validate_model = field_validator("model")(_validate_model)


@app.post("/ai/analyse")
async def ai_analyse(
    body: AnalyseRequest,
    licence: db.sqlite3.Row = Depends(_require_licence),
):
    import anthropic, json

    # Import shared prompt/tool definitions from the app source
    # These are embedded here so the backend is self-contained
    from ai_defs import SYSTEM_PROMPT, RECOMMENDATION_TOOL

    client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)

    map_section = json.dumps(body.map_context, indent=2) if body.map_context else "Not provided"
    rom_section = ""
    if body.rom_context:
        rom_section = (
            "\n\nROM identification context:\n"
            + json.dumps(body.rom_context, indent=2)
        )

    user_msg = (
        "Analyse this engine log and recommend calibration adjustments.\n\n"
        f"Log summary:\n{json.dumps(body.log_summary, indent=2)}\n\n"
        f"Current map context:\n{map_section}"
        f"{rom_section}\n\n"
        "Be conservative. Prioritise engine safety. "
        "Use the submit_tuning_recommendation tool."
    )

    response = client.messages.create(
        model       = body.model,
        max_tokens  = 2048,
        system      = _cached_system(SYSTEM_PROMPT),
        messages    = [{"role": "user", "content": user_msg}],
        tools       = [RECOMMENDATION_TOOL],
        tool_choice = {"type": "any"},
    )

    tool_input = None
    for block in response.content:
        if block.type == "tool_use":
            tool_input = block.input
            break

    if tool_input is None:
        raise HTTPException(status_code=502, detail="AI model returned no structured output")

    tokens = response.usage.input_tokens + response.usage.output_tokens
    db.log_request(licence["licence_key"], tokens)

    return {"recommendation": tool_input, "tokens": tokens}


class AskRequest(BaseModel):
    prompt: str
    model:  str = "claude-sonnet-5"

    _validate_model = field_validator("model")(_validate_model)


@app.post("/ai/ask")
async def ai_ask(
    body: AskRequest,
    licence: db.sqlite3.Row = Depends(_require_licence),
):
    """Plain prompt -> text proxy, no tools/history. Backs quick one-off
    AI calls (e.g. ui/ai_expanded_panel.py's tabs) that don't need the
    structured tuning-recommendation schema."""
    import anthropic

    client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model      = body.model,
        max_tokens = 1024,
        messages   = [{"role": "user", "content": body.prompt}],
    )
    tokens = response.usage.input_tokens + response.usage.output_tokens
    db.log_request(licence["licence_key"], tokens)

    if not response.content or response.content[0].type != "text":
        raise HTTPException(status_code=502, detail="AI model returned no text output")
    return {"text": response.content[0].text, "tokens": tokens}


class NameMapsRequest(BaseModel):
    candidates: list[dict]
    ecu_hint:   str = ""
    model:      str = "claude-sonnet-5"

    _validate_model = field_validator("model")(_validate_model)


@app.post("/ai/name-maps")
async def ai_name_maps(
    body: NameMapsRequest,
    licence: db.sqlite3.Row = Depends(_require_licence),
):
    """Proxy for ai/map_namer.py::MapNamer — names/describes detected ROM tables."""
    import anthropic, json

    from map_defs import NAMING_SYSTEM_PROMPT, NAMING_TOOL

    client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)

    hint_line = f"\nECU hint: {body.ecu_hint}\n" if body.ecu_hint else ""
    user_msg  = (
        f"{hint_line}\n"
        "Name and describe each of these detected ROM calibration tables:\n\n"
        + json.dumps(body.candidates, indent=2)
        + "\n\nCall submit_map_names with your analysis."
    )

    response = client.messages.create(
        model       = body.model,
        max_tokens  = 4096,
        system      = _cached_system(NAMING_SYSTEM_PROMPT),
        messages    = [{"role": "user", "content": user_msg}],
        tools       = [NAMING_TOOL],
        tool_choice = {"type": "any"},
    )

    tool_input = None
    for block in response.content:
        if block.type == "tool_use":
            tool_input = block.input
            break
    if tool_input is None:
        raise HTTPException(status_code=502, detail="AI model returned no structured output")

    tokens = response.usage.input_tokens + response.usage.output_tokens
    db.log_request(licence["licence_key"], tokens)

    return {"tables": tool_input.get("tables", []), "tokens": tokens}


class ExplainMapRequest(BaseModel):
    payload: dict
    model:   str = "claude-sonnet-5"

    _validate_model = field_validator("model")(_validate_model)


@app.post("/ai/explain-map")
async def ai_explain_map(
    body: ExplainMapRequest,
    licence: db.sqlite3.Row = Depends(_require_licence),
):
    """Proxy for ai/map_explainer.py::MapExplainer — explains a single calibration table."""
    import anthropic, json

    from map_defs import EXPLAIN_SYSTEM_PROMPT, EXPLAIN_TOOL

    client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)

    user_msg = (
        "Explain this ECU calibration table:\n\n"
        + json.dumps(body.payload, indent=2)
        + "\n\nCall submit_map_explanation with your analysis."
    )

    response = client.messages.create(
        model       = body.model,
        max_tokens  = 2048,
        system      = _cached_system(EXPLAIN_SYSTEM_PROMPT),
        messages    = [{"role": "user", "content": user_msg}],
        tools       = [EXPLAIN_TOOL],
        tool_choice = {"type": "any"},
    )

    tool_input = None
    for block in response.content:
        if block.type == "tool_use":
            tool_input = block.input
            break
    if tool_input is None:
        raise HTTPException(status_code=502, detail="AI model returned no structured output")

    tokens = response.usage.input_tokens + response.usage.output_tokens
    db.log_request(licence["licence_key"], tokens)

    return {"explanation": tool_input, "tokens": tokens}


class ChatRequest(BaseModel):
    messages:    list[dict]
    tools:       list[dict] = []
    tool_choice: dict = {"type": "auto"}
    model:       str = "claude-sonnet-5"

    _validate_model = field_validator("model")(_validate_model)


@app.post("/ai/chat")
async def ai_chat(
    body: ChatRequest,
    licence: db.sqlite3.Row = Depends(_require_licence),
):
    """
    Proxy for ai/tuning_agent.py::TuningAgent.chat() — Dora's conversational
    tool-using loop. Thin relay, NOT a structured-output endpoint like
    /ai/analyse: the client owns and executes the tools (they need local
    ECU/ROM state this backend doesn't have), so this just forwards
    whatever tools/tool_choice/messages the client sends and returns the
    raw response content for the client to interpret and act on.
    """
    import anthropic

    from dora_defs import DORA_SYSTEM_PROMPT

    client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)

    response = client.messages.create(
        model       = body.model,
        max_tokens  = 2048,
        system      = _cached_system(DORA_SYSTEM_PROMPT),
        messages    = body.messages,
        tools       = body.tools,
        tool_choice = body.tool_choice,
    )

    tokens = response.usage.input_tokens + response.usage.output_tokens
    db.log_request(licence["licence_key"], tokens)

    return {
        "content":     [block.model_dump() for block in response.content],
        "stop_reason": response.stop_reason,
        "tokens":      tokens,
    }


# ── Voice proxy ───────────────────────────────────────────────────────────────
#
# Voice (STT/TTS) is metered through the same licence key as the Claude
# calls above, per the product decision to bill it like the rest of AI
# usage rather than requiring users' own OpenAI/ElevenLabs accounts. The
# provider keys live only here — the desktop client never sees them.

_MAX_VOICE_UPLOAD_BYTES = 25 * 1024 * 1024   # matches OpenAI's own Whisper upload limit


@app.post("/voice/transcribe")
async def voice_transcribe(
    request: Request,
    file: UploadFile = File(...),
    licence: db.sqlite3.Row = Depends(_require_licence),
):
    """Proxy for ai/voice.py::transcribe — speech-to-text via OpenAI."""
    import io
    import wave

    import httpx

    # Reject up front when the client sends an honest Content-Length, so an
    # oversized upload doesn't even get buffered; re-checked after read()
    # as a backstop for chunked-encoding uploads with no Content-Length.
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_VOICE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large (max 25 MB)")

    audio_bytes = await file.read()
    if len(audio_bytes) > _MAX_VOICE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large (max 25 MB)")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {cfg.OPENAI_API_KEY}"},
                files={"file": (file.filename or "audio.wav", audio_bytes, file.content_type or "audio/wav")},
                data={"model": cfg.OPENAI_TRANSCRIBE_MODEL},
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI transcription error: {exc.response.text}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach OpenAI: {exc}") from exc

    text = resp.json().get("text", "")

    # Duration-based metering — cheap and accurate for WAV input, no need
    # to trust/parse provider usage fields that vary by model.
    try:
        with wave.open(io.BytesIO(audio_bytes)) as w:
            duration_s = w.getnframes() / max(w.getframerate(), 1)
    except (wave.Error, EOFError):
        duration_s = 0.0
    db.log_request(licence["licence_key"], round(duration_s), kind="voice_stt")

    return {"text": text}


class SynthesizeRequest(BaseModel):
    text:     str
    voice_id: str = ""


@app.post("/voice/synthesize")
async def voice_synthesize(
    body: SynthesizeRequest,
    licence: db.sqlite3.Row = Depends(_require_licence),
):
    """Proxy for ai/voice.py::synthesize — text-to-speech via ElevenLabs.
    Returns raw 24kHz 16-bit mono PCM (output_format=pcm_24000) so the
    client can play it directly with no MP3 decoder dependency."""
    import httpx

    voice_id = body.voice_id or cfg.ELEVENLABS_VOICE_ID

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                params={"output_format": "pcm_24000"},
                headers={"xi-api-key": cfg.ELEVENLABS_API_KEY},
                json={"text": body.text, "model_id": cfg.ELEVENLABS_MODEL_ID},
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"ElevenLabs TTS error: {exc.response.text}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach ElevenLabs: {exc}") from exc

    db.log_request(licence["licence_key"], len(body.text), kind="voice_tts")

    return Response(content=resp.content, media_type="application/octet-stream")


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin/licences", dependencies=[Depends(_require_admin)])
async def admin_list():
    rows = db.list_licences()
    return [dict(r) for r in rows]


class IssueRequest(BaseModel):
    email: EmailStr
    note: str = ""


@app.post("/admin/issue", dependencies=[Depends(_require_admin)])
async def admin_issue(body: IssueRequest):
    """Manually issue a licence key (for pilots, comps, support)."""
    key = db.create_licence(email=body.email, note=body.note or "manual")
    try:
        from email_sender import send_licence_email
        send_licence_email(body.email, key)
        emailed = True
    except Exception as exc:
        emailed = False
        print(f"Email failed: {exc}")
    return {"licence_key": key, "emailed": emailed}
