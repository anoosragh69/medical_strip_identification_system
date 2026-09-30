const UPLOAD_ENDPOINT = "/upload";

const els = {
  camera: document.getElementById("camera-input"),
  gallery: document.getElementById("gallery-input"),
  previewWrap: document.getElementById("preview-wrap"),
  preview: document.getElementById("preview"),
  status: document.getElementById("status"),
  result: document.getElementById("result"),
  raw: document.getElementById("raw"),
  rawJson: document.getElementById("raw-json"),
  name: document.getElementById("result-name"),
  generic: document.getElementById("result-generic"),
  tier: document.getElementById("result-tier"),
  confidence: document.getElementById("result-confidence"),
  uses: document.getElementById("result-uses"),
  dosage: document.getElementById("result-dosage"),
  sideEffects: document.getElementById("result-side-effects"),
};

function setStatus(message, kind) {
  els.status.hidden = !message;
  els.status.textContent = message || "";
  els.status.className = `status ${kind || ""}`.trim();
}

function showPreview(file) {
  if (els.preview.src) URL.revokeObjectURL(els.preview.src);
  els.preview.src = URL.createObjectURL(file);
  els.previewWrap.hidden = false;
}

async function upload(file) {
  showPreview(file);
  els.result.hidden = true;
  els.raw.hidden = true;
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

  els.raw.hidden = false;
  els.rawJson.textContent = JSON.stringify(data, null, 2);

  if (!data.matched) {
    setStatus("Couldn't identify that strip — retake the photo with better lighting or less glare.", "warn");
    return;
  }

  setStatus("");
  renderResult(data);
}

function renderResult(data) {
  els.name.textContent = data.name || "Unknown medicine";
  els.generic.textContent = data.generic_name || "";
  els.tier.textContent = `identified via ${data.source_tier}`;
  els.confidence.textContent =
    typeof data.confidence === "number" ? `${Math.round(data.confidence * 100)}% confidence` : "";
  els.uses.textContent = data.uses || "—";
  els.dosage.textContent = data.dosage || "—";
  els.sideEffects.textContent = data.side_effects || "—";
  els.result.hidden = false;
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
