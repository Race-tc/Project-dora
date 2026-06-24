// ── Config ─────────────────────────────────────────────────────────────────
// Replace this with your deployed backend URL once you have one.
const BACKEND_URL = "https://api.projectdora.com";

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
    showError("Please enter a valid email address.");
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
    showError(err.message || "Something went wrong. Please try again.");
    submitEl.disabled = false;
    submitEl.textContent = "Continue to Payment →";
  }
}

function showError(msg) {
  const el = document.getElementById("checkout-error");
  el.textContent = msg;
  el.classList.remove("hidden");
}
