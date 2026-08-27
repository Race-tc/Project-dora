// ── Config ─────────────────────────────────────────────────────────────────
// Auto-detects localhost so the same file works for local testing and prod.
// Replace the production fallback with your deployed backend URL once you have one.
const BACKEND_URL = ["localhost", "127.0.0.1"].includes(window.location.hostname)
  ? "http://localhost:8000"
  : "https://project-dora-production.up.railway.app";

// Replace this with a real installer download link (e.g. GitHub releases).
const INSTALLER_URL = "#";  // TODO: add your installer download link

// ── Wire up download button ────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  const dlBtn = document.getElementById("download-btn");
  if (dlBtn && INSTALLER_URL !== "#") {
    dlBtn.href = INSTALLER_URL;
    dlBtn.download = "DoraSetup.exe";
  }
});

// ── Checkout flow ──────────────────────────────────────────────────────────

function startCheckout() {
  document.getElementById("checkout-overlay").classList.remove("hidden");
  document.getElementById("checkout-email").focus();
  document.getElementById("checkout-error").classList.add("hidden");
  document.getElementById("checkout-email").value = "";
}

function closeModal() {
  document.getElementById("checkout-overlay").classList.add("hidden");
}

// Close on backdrop click
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("checkout-overlay").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeModal();
  });

  // Allow Enter key to submit
  document.getElementById("checkout-email").addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitCheckout();
  });
});

async function submitCheckout() {
  const emailEl  = document.getElementById("checkout-email");
  const submitEl = document.getElementById("modal-submit");
  const errorEl  = document.getElementById("checkout-error");
  const email    = emailEl.value.trim();

  // Basic validation
  if (!email || !email.includes("@")) {
    showError("checkout-error", "Please enter a valid email address.");
    return;
  }

  // Loading state
  submitEl.disabled = true;
  submitEl.textContent = "Connecting to Stripe…";
  errorEl.classList.add("hidden");

  try {
    const resp = await fetch(`${BACKEND_URL}/checkout`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ email }),
    });

    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || `Server error (${resp.status})`);
    }

    const { checkout_url } = await resp.json();
    // Redirect to Stripe Checkout
    window.location.href = checkout_url;

  } catch (err) {
    showError("checkout-error", err.message || "Something went wrong. Please try again.");
    submitEl.disabled = false;
    submitEl.textContent = "Continue to Payment →";
  }
}

function showError(elId, msg) {
  const el = document.getElementById(elId);
  el.textContent = msg;
  el.classList.remove("hidden");
}

// ── Waitlist flow ────────────────────────────────────────────────────────────
// Checkout is paused pre-launch — every "buy" CTA on the page currently
// opens this instead. Re-point them at startCheckout() once the beta ends
// and paid signup reopens; the checkout modal/flow above is untouched.
//
// The form itself is embedded Cognito Forms (see the modal markup) — it
// handles its own validation, submission, and success state. Cognito's
// webhook relays each submission to POST /waitlist/cognito on our backend,
// so /admin/launch-beta still has every signup to work from on launch day.

function openWaitlist() {
  document.getElementById("waitlist-overlay").classList.remove("hidden");
}

function closeWaitlistModal() {
  document.getElementById("waitlist-overlay").classList.add("hidden");
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("waitlist-overlay").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeWaitlistModal();
  });
});
