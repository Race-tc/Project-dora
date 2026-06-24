"""
backend/main.py — DORA subscription backend.

Routes:
  POST /checkout          Create a Stripe Checkout session (garage signs up)
  POST /webhook           Stripe webhook (subscription events)
  POST /ai/analyse        Proxy AI analysis call (requires licence key)
  GET  /validate/{key}    Check if a licence key is active
  GET  /portal/{key}      Generate a Stripe customer portal link
  GET  /admin/licences    List all licences (requires admin token)
  POST /admin/issue       Manually issue a licence (requires admin token)
"""
from __future__ import annotations

import stripe
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import backend.database as db
from backend.settings import cfg

stripe.api_key = cfg.STRIPE_SECRET_KEY

app = FastAPI(title="DORA Backend", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _require_admin(x_admin_token: str = Header(...)):
    if x_admin_token != cfg.ADMIN_TOKEN:
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
    email: str


@app.post("/checkout")
async def create_checkout(body: CheckoutRequest):
    """Return a Stripe Checkout URL. Garage visits it to subscribe."""
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="subscription",
        customer_email=body.email,
        line_items=[{"price": cfg.STRIPE_PRICE_ID, "quantity": 1}],
        success_url=f"{cfg.SITE_URL}/success.html?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{cfg.SITE_URL}/cancelled.html",
        metadata={"email": body.email},
    )
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
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    etype = event["type"]
    data  = event["data"]["object"]

    if etype == "checkout.session.completed":
        # New subscriber — create licence and email it
        email    = data.get("customer_email") or data["metadata"].get("email", "")
        cust_id  = data.get("customer")
        sub_id   = data.get("subscription")
        key      = db.create_licence(
            email=email,
            stripe_customer_id=cust_id,
            stripe_subscription_id=sub_id,
        )
        try:
            from backend.email_sender import send_licence_email
            send_licence_email(email, key)
        except Exception as exc:
            # Log but don't fail the webhook — key is in the DB
            print(f"Email failed for {email}: {exc}")

    elif etype in ("customer.subscription.deleted",
                   "customer.subscription.paused"):
        db.set_status(data["id"], "cancelled")

    elif etype == "customer.subscription.updated":
        stripe_status = data.get("status", "active")
        dora_status   = "active" if stripe_status == "active" else "suspended"
        db.set_status(data["id"], dora_status)

    elif etype == "invoice.payment_failed":
        sub_id = data.get("subscription")
        if sub_id:
            db.set_status(sub_id, "suspended")

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
    session = stripe.billing_portal.Session.create(
        customer=row["stripe_customer_id"],
        return_url=f"{cfg.BASE_URL}/",
    )
    return {"portal_url": session.url}


# ── AI proxy ──────────────────────────────────────────────────────────────────

class AnalyseRequest(BaseModel):
    log_summary:  dict
    rom_context:  dict = {}
    map_context:  dict = {}
    model:        str  = "claude-opus-4-6"


@app.post("/ai/analyse")
async def ai_analyse(
    body: AnalyseRequest,
    licence: db.sqlite3.Row = Depends(_require_licence),
):
    import anthropic, json

    # Import shared prompt/tool definitions from the app source
    # These are embedded here so the backend is self-contained
    from backend.ai_defs import SYSTEM_PROMPT, RECOMMENDATION_TOOL

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
        system      = SYSTEM_PROMPT,
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


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin/licences", dependencies=[Depends(_require_admin)])
async def admin_list():
    rows = db.list_licences()
    return [dict(r) for r in rows]


class IssueRequest(BaseModel):
    email: str
    note: str = ""


@app.post("/admin/issue", dependencies=[Depends(_require_admin)])
async def admin_issue(body: IssueRequest):
    """Manually issue a licence key (for pilots, comps, support)."""
    key = db.create_licence(email=body.email, note=body.note or "manual")
    try:
        from backend.email_sender import send_licence_email
        send_licence_email(body.email, key)
        emailed = True
    except Exception as exc:
        emailed = False
        print(f"Email failed: {exc}")
    return {"licence_key": key, "emailed": emailed}
