const UPLOAD_ENDPOINT = "/upload";

const els = {
  camera: document.getElementById("camera-input"),
  gallery: document.getElementById("gallery-input"),
  previewWrap: document.getElementById("preview-wrap"),
  preview: document.getElementById("preview"),
  status: document.getElementById("status"),
  result: document.getElementById("result"),
  notFound: document.getElementById("not-found"),
  retryBtn: document.getElementById("retry-btn"),
  raw: document.getElementById("raw"),
  rawJson: document.getElementById("raw-json"),
  name: document.getElementById("result-name"),
  generic: document.getElementById("result-generic"),
  tier: document.getElementById("result-tier"),
  confidence: document.getElementById("result-confidence"),
  uses: document.getElementById("result-uses"),
  dosage: document.getElementById("result-dosage"),
  sideEffects: document.getElementById("result-side-effects"),
  ocrWrap: document.getElementById("result-ocr"),
  ocrText: document.getElementById("result-ocr-text"),
};

function setStatus(message, kind) {
  els.status.hidden = !message;
  els.status.textContent = message || "";
  els.status.className = `status ${kind || ""}`.trim();
}

function hideResults() {
  els.result.hidden = true;
  els.notFound.hidden = true;
  els.raw.hidden = true;
}

function showPreview(file) {
  if (els.preview.src) URL.revokeObjectURL(els.preview.src);
  els.preview.src = URL.createObjectURL(file);
  els.previewWrap.hidden = false;
}

async function upload(file) {
  // Validate before sending
  if (!file.type.startsWith("image/")) {
    setStatus("Please select an image file.", "error");
    return;
  }
  if (file.size > 8 * 1024 * 1024) {
    setStatus("Image is too large (max 8 MB). Try a lower resolution.", "error");
    return;
  }

  showPreview(file);
  hideResults();
  setStatus("Reading strip…", "busy");

  const form = new FormData();
  form.append("file", file, file.name || "capture.jpg");

  let data;
  try {
    const response = await fetch(UPLOAD_ENDPOINT, { method: "POST", body: form });
    data = await response.json();
    if (!response.ok) throw new Error(data.note || `server responded ${response.status}`);
  } catch (error) {
    setStatus(`Upload failed: ${error.message}`, "error");
    return;
  }

  // Always show raw JSON
  els.raw.hidden = false;
  els.rawJson.textContent = JSON.stringify(data, null, 2);

  if (!data.matched) {
    setStatus("", "");
    showNotFound(data);
    return;
  }

  setStatus("");
  renderResult(data);
}

function showNotFound(data) {
  els.notFound.hidden = false;
  els.result.hidden = true;

  // If there's OCR text, show it in raw so the user can see what was read
  if (data.ocr_raw_text) {
    els.rawJson.textContent = JSON.stringify(data, null, 2);
    els.raw.hidden = false;
  }
}

function renderResult(data) {
  els.name.textContent = data.name || "Unknown medicine";
  els.generic.textContent = data.generic_name || "";

  // Tier badge with color class
  const tierLabel = data.source_tier || "unknown";
  els.tier.textContent = `identified via ${tierLabel}`;
  els.tier.className = `tier tier-${tierLabel}`;

  els.confidence.textContent =
    typeof data.confidence === "number" ? `${Math.round(data.confidence * 100)}% confidence` : "";
  els.uses.textContent = data.uses || "—";
  els.dosage.textContent = data.dosage || "—";
  els.sideEffects.textContent = data.side_effects || "—";

  // Show OCR text if available
  if (data.ocr_raw_text && els.ocrWrap && els.ocrText) {
    els.ocrText.textContent = data.ocr_raw_text;
    els.ocrWrap.hidden = false;
  } else if (els.ocrWrap) {
    els.ocrWrap.hidden = true;
  }

  els.result.hidden = false;
  els.notFound.hidden = true;
}

function bind(input) {
  input.addEventListener("change", () => {
    const file = input.files && input.files[0];
    if (file) upload(file);
    input.value = "";
  });
}

bind(els.camera);
bind(els.gallery);

// Retry button triggers the camera input
if (els.retryBtn) {
  els.retryBtn.addEventListener("click", () => {
    els.camera.click();
  });
}
