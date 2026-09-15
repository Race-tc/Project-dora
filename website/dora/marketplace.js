// ── Config ─────────────────────────────────────────────────────────────────
const BACKEND_URL = ["localhost", "127.0.0.1"].includes(window.location.hostname)
  ? "http://localhost:8000"
  : "https://project-dora-production.up.railway.app";

const LICENCE_STORAGE_KEY = "dora_licence_key";

let _allTunes = [];
let _searchSeq = 0;   // guards against a slower earlier search response
                      // overwriting a faster later one (out-of-order fetches)
const _EMPTY_TEXT = "No tunes found. Be the first to upload one.";

// ── Load & render ─────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  loadTunes();

  const search = document.getElementById("mkt-search");
  let debounce;
  search.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => loadTunes(search.value.trim()), 250);
  });

  const savedKey = localStorage.getItem(LICENCE_STORAGE_KEY);
  if (savedKey) document.getElementById("up-licence").value = savedKey;

  document.getElementById("upload-overlay").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeUpload();
  });
  document.getElementById("detail-overlay").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeDetail();
  });

  const fileInput = document.getElementById("up-file");
  fileInput.addEventListener("change", () => {
    const label = document.getElementById("up-file-name");
    label.textContent = fileInput.files.length ? fileInput.files[0].name : label.textContent;
  });
});

async function loadTunes(q = "") {
  const grid  = document.getElementById("mkt-grid");
  const empty = document.getElementById("mkt-empty");
  const count = document.getElementById("mkt-count");

  // Rapid typing can fire several requests; a slower earlier one resolving
  // after a faster later one would otherwise repaint the grid with stale
  // results. Only the most recently *started* request is allowed to render.
  const seq = ++_searchSeq;

  try {
    const url = q ? `${BACKEND_URL}/marketplace/tunes?q=${encodeURIComponent(q)}`
                  : `${BACKEND_URL}/marketplace/tunes`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`Server error (${resp.status})`);
    const tunes = await resp.json();
    if (seq !== _searchSeq) return;   // a newer search has since started

    _allTunes = tunes;
    count.textContent = `${_allTunes.length} tune${_allTunes.length === 1 ? "" : "s"}`;
    grid.innerHTML = "";
    empty.textContent = _EMPTY_TEXT;
    empty.classList.toggle("hidden", _allTunes.length > 0);
    _allTunes.forEach((tune) => grid.appendChild(renderCard(tune)));
  } catch (err) {
    if (seq !== _searchSeq) return;
    count.textContent = "Couldn't load tunes";
    grid.innerHTML = "";
    empty.textContent = "Couldn't reach the marketplace right now. Try again shortly.";
    empty.classList.remove("hidden");
  }
}

function renderCard(tune) {
  const card = document.createElement("div");
  card.className = "mkt-card";
  card.onclick = () => openDetail(tune.id);

  const vehicle = [tune.vehicle_make, tune.vehicle_model, tune.vehicle_year].filter(Boolean).join(" ") || "Vehicle not specified";
  const gainLine = hpLine(tune);
  const tags = (tune.tags || []).slice(0, 3).map((t) => `<span class="mkt-tag">${escapeHtml(t)}</span>`).join("");

  card.innerHTML = `
    <h3 class="mkt-card-title">${escapeHtml(tune.title)}</h3>
    <div class="mkt-card-author">${escapeHtml(tune.author_name)}</div>
    <div class="mkt-card-vehicle">${escapeHtml(vehicle)}</div>
    ${gainLine ? `<div class="mkt-card-gain">${escapeHtml(gainLine)}</div>` : ""}
    <div class="mkt-card-meta">${tune.downloads.toLocaleString()} download${tune.downloads === 1 ? "" : "s"}</div>
    <div class="mkt-card-tags">${tags}</div>
  `;
  return card;
}

function hpLine(tune) {
  if (tune.power_gain) return tune.power_gain;
  if (tune.hp_before != null && tune.hp_after != null) return `${tune.hp_before} → ${tune.hp_after} hp`;
  return "";
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s ?? "";
  return div.innerHTML;
}

// ── Detail modal ─────────────────────────────────────────────────────────

function openDetail(id) {
  const tune = _allTunes.find((t) => t.id === id);
  if (!tune) return;

  const vehicle = [tune.vehicle_make, tune.vehicle_model, tune.vehicle_year].filter(Boolean).join(" ") || "—";
  const gainLine = hpLine(tune) || "—";
  const tags = (tune.tags || []).map((t) => `<span class="mkt-tag">${escapeHtml(t)}</span>`).join("");

  document.getElementById("detail-body").innerHTML = `
    <h3>${escapeHtml(tune.title)}</h3>
    <p style="color: var(--accent-lt); font-weight:700; font-size:13px; margin-bottom:14px;">${escapeHtml(tune.author_name)}</p>
    <div class="mkt-detail-grid">
      <div><span class="mkt-detail-label">Vehicle</span>${escapeHtml(vehicle)}</div>
      <div><span class="mkt-detail-label">ECU</span>${escapeHtml(tune.ecu_type || "—")}</div>
      <div><span class="mkt-detail-label">Engine</span>${escapeHtml(tune.engine || "—")}</div>
      <div><span class="mkt-detail-label">Power</span>${escapeHtml(gainLine)}</div>
      <div><span class="mkt-detail-label">Mods</span>${escapeHtml(tune.mods || "—")}</div>
      <div><span class="mkt-detail-label">Downloads</span>${tune.downloads.toLocaleString()}</div>
    </div>
    ${tags ? `<div class="mkt-card-tags" style="margin: 12px 0;">${tags}</div>` : ""}
    ${tune.description ? `<p style="font-size:14px; color: var(--fg-dim); line-height:1.7; margin: 14px 0;">${escapeHtml(tune.description)}</p>` : ""}
    <div class="mkt-disclaimer" style="margin: 16px 0;">
      ⚠ Community-submitted, not verified by DORA. Use at your own risk.
    </div>
    <div class="modal-btns">
      <a class="btn btn-lg btn-full" href="${BACKEND_URL}/marketplace/tunes/${tune.id}/download">Download (${escapeHtml(tune.filename)})</a>
      <button class="btn-ghost-sm" onclick="closeDetail()">Close</button>
    </div>
  `;
  document.getElementById("detail-overlay").classList.remove("hidden");
}

function closeDetail() {
  document.getElementById("detail-overlay").classList.add("hidden");
}

// ── Upload modal ─────────────────────────────────────────────────────────

function openUpload() {
  document.getElementById("upload-form").classList.remove("hidden");
  document.getElementById("upload-success").classList.add("hidden");
  document.getElementById("upload-error").classList.add("hidden");
  document.getElementById("upload-overlay").classList.remove("hidden");
}

function closeUpload() {
  document.getElementById("upload-overlay").classList.add("hidden");
  _resetUploadForm();
}

const _UPLOAD_FILE_PLACEHOLDER =
  "Choose tune file… (.bin .hex .ols .kp .adf .map .cal .a2l .xdf .mpc .dam .json .rom .zip, max 20MB)";

function _resetUploadForm() {
  // Deliberately does NOT clear up-licence — it's meant to persist across
  // uploads in the same session (pre-filled from localStorage on load).
  // Without this, the form kept every field's value (including the
  // previously-selected File object) across opens: uploading a second tune
  // without touching every field would silently re-send the first tune's
  // file under the new metadata.
  const textFields = [
    "up-author", "up-title", "up-make", "up-model", "up-year", "up-ecu",
    "up-engine", "up-mods", "up-gain", "up-hp-before", "up-hp-after",
    "up-tags", "up-desc",
  ];
  textFields.forEach((id) => { document.getElementById(id).value = ""; });
  document.getElementById("up-file").value = "";
  document.getElementById("up-file-name").textContent = _UPLOAD_FILE_PLACEHOLDER;
}

async function submitUpload() {
  const licence = document.getElementById("up-licence").value.trim();
  const title   = document.getElementById("up-title").value.trim();
  const file    = document.getElementById("up-file").files[0];
  const errorEl = document.getElementById("upload-error");
  const submitEl = document.getElementById("upload-submit");

  if (!licence) return showUploadError("Enter your DORA licence key.");
  if (!title) return showUploadError("Give your tune a title.");
  if (!file) return showUploadError("Choose a tune file to upload.");

  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  form.append("author_name", document.getElementById("up-author").value.trim());
  form.append("vehicle_make", document.getElementById("up-make").value.trim());
  form.append("vehicle_model", document.getElementById("up-model").value.trim());
  form.append("vehicle_year", document.getElementById("up-year").value.trim());
  form.append("ecu_type", document.getElementById("up-ecu").value.trim());
  form.append("engine", document.getElementById("up-engine").value.trim());
  form.append("mods", document.getElementById("up-mods").value.trim());
  form.append("power_gain", document.getElementById("up-gain").value.trim());
  const hpBefore = document.getElementById("up-hp-before").value;
  const hpAfter  = document.getElementById("up-hp-after").value;
  if (hpBefore) form.append("hp_before", hpBefore);
  if (hpAfter)  form.append("hp_after", hpAfter);
  form.append("description", document.getElementById("up-desc").value.trim());
  form.append("tags", document.getElementById("up-tags").value.trim());

  submitEl.disabled = true;
  submitEl.textContent = "Uploading…";
  errorEl.classList.add("hidden");

  try {
    const resp = await fetch(`${BACKEND_URL}/marketplace/tunes`, {
      method: "POST",
      headers: { "X-Licence-Key": licence },
      body: form,
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || `Server error (${resp.status})`);
    }

    localStorage.setItem(LICENCE_STORAGE_KEY, licence);
    document.getElementById("upload-form").classList.add("hidden");
    document.getElementById("upload-success").classList.remove("hidden");
    loadTunes(document.getElementById("mkt-search").value.trim());
  } catch (err) {
    showUploadError(err.message || "Something went wrong. Please try again.");
  } finally {
    submitEl.disabled = false;
    submitEl.textContent = "Upload Tune →";
  }
}

function showUploadError(msg) {
  const el = document.getElementById("upload-error");
  el.textContent = msg;
  el.classList.remove("hidden");
}
