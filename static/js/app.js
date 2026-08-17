const dropzone = document.getElementById("dropzone");
const dropzoneInner = document.getElementById("dropzoneInner");
const fileInput = document.getElementById("fileInput");
const previewVideo = document.getElementById("previewVideo");
const analyzeBtn = document.getElementById("analyzeBtn");
const progressWrap = document.getElementById("progressWrap");
const progressFill = document.getElementById("progressFill");
const progressLabel = document.getElementById("progressLabel");
const statusPill = document.getElementById("statusPill");

const emptyState = document.getElementById("emptyState");
const readout = document.getElementById("readout");

const gaugeScore = document.getElementById("gaugeScore");
const verdictLabel = document.getElementById("verdictLabel");
const verdictDesc = document.getElementById("verdictDesc");
const videoMeter = document.getElementById("videoMeter");
const videoMeterVal = document.getElementById("videoMeterVal");
const audioMeter = document.getElementById("audioMeter");
const audioMeterVal = document.getElementById("audioMeterVal");

const stageImg = document.getElementById("stageImg");
const signalBars = document.getElementById("signalBars");
const timelineCanvas = document.getElementById("timelineCanvas");
const audioStage = document.getElementById("audioStage");
const spectrogramImg = document.getElementById("spectrogramImg");
const audioSignals = document.getElementById("audioSignals");

let selectedFile = null;
let lastPayload = null;
let selectedFrameIdx = 0;

const GAUGE_ARC_LEN = 251.3; // length of the 180deg speedometer arc, r=80

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

// ---------------- file selection ----------------

dropzone.addEventListener("click", () => fileInput.click());
["dragenter", "dragover"].forEach(evt => dropzone.addEventListener(evt, e => { e.preventDefault(); dropzone.classList.add("drag"); }));
["dragleave", "drop"].forEach(evt => dropzone.addEventListener(evt, e => { e.preventDefault(); dropzone.classList.remove("drag"); }));
dropzone.addEventListener("drop", e => { const f = e.dataTransfer.files[0]; if (f) handleFile(f); });
fileInput.addEventListener("change", e => { if (e.target.files[0]) handleFile(e.target.files[0]); });

function handleFile(file) {
  selectedFile = file;
  previewVideo.src = URL.createObjectURL(file);
  previewVideo.hidden = false;
  dropzoneInner.hidden = true;
  analyzeBtn.disabled = false;
  setStatus("idle", "ready");
}

// ---------------- analyze ----------------

analyzeBtn.addEventListener("click", runAnalysis);

async function runAnalysis() {
  if (!selectedFile) return;
  const form = new FormData();
  form.append("video", selectedFile);
  await runScan(() => fetch("/api/analyze", { method: "POST", body: form }), analyzeBtn);
}

const urlInput = document.getElementById("urlInput");
const urlScanBtn = document.getElementById("urlScanBtn");
urlScanBtn.addEventListener("click", runUrlAnalysis);
urlInput.addEventListener("keydown", e => { if (e.key === "Enter") runUrlAnalysis(); });

async function runUrlAnalysis() {
  const url = urlInput.value.trim();
  if (!url) return;
  await runScan(() => fetch("/api/analyze-url", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  }), urlScanBtn);
}

const PENDING_JOB_KEY = "trace_pending_job";

async function runScan(fetchCall, triggerBtn) {
  triggerBtn.disabled = true;
  dropzone.classList.add("scanning");
  progressWrap.hidden = false;
  progressLabel.textContent = "Starting scan…";
  setStatus("busy", "queued");

  try {
    const res = await fetchCall();
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not start scan");
    localStorage.setItem(PENDING_JOB_KEY, data.job_id);
    pollJob(data.job_id, triggerBtn);
  } catch (err) {
    setStatus("idle", "error");
    alert(err.message);
    dropzone.classList.remove("scanning");
    progressWrap.hidden = true;
    triggerBtn.disabled = false;
  }
}

async function pollJob(jobId, triggerBtn) {
  setStatus("busy", "scanning — safe to browse away");
  animateFakeProgress();
  progressLabel.textContent = "Scanning in the background — you can browse elsewhere, this will keep running.";

  const poll = async () => {
    try {
      const res = await fetch(`/api/job/${jobId}`);
      const data = await res.json();
      if (!res.ok || data.status === "error") {
        throw new Error(data.error || "Analysis failed");
      }
      if (data.status === "done") {
        localStorage.removeItem(PENDING_JOB_KEY);
        lastPayload = data.result;
        renderResults(data.result);
        setStatus(data.result.verdict === "FAKE" ? "fake" : "done", data.result.verdict ? data.result.verdict.toLowerCase() : "complete");
        finishScanUI(triggerBtn);
        return;
      }
      setTimeout(poll, 2000);
    } catch (err) {
      localStorage.removeItem(PENDING_JOB_KEY);
      setStatus("idle", "error");
      alert(err.message);
      finishScanUI(triggerBtn);
    }
  };
  poll();
}

function finishScanUI(triggerBtn) {
  dropzone.classList.remove("scanning");
  progressWrap.hidden = true;
  if (triggerBtn) triggerBtn.disabled = false;
}

// (resumePendingJob moved to end of file - see bottom - to avoid referencing
// `let`-declared variables like fakeProgressTimer before their declaration runs)

function animateGauge(pct, verdict) {
  const arc = document.querySelector(".speedo-arc");
  const needle = document.getElementById("speedoNeedle");
  const offset = GAUGE_ARC_LEN - (pct / 100) * GAUGE_ARC_LEN;
  arc.style.strokeDashoffset = offset;

  const angle = -90 + (pct / 100) * 180;
  needle.style.transform = `rotate(${angle}deg)`;

  // animated count-up for the number
  const start = performance.now();
  const duration = 900;
  function tick(now) {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    gaugeScore.textContent = (pct * eased).toFixed(1) + "%";
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

function renderCredentials(check) {
  const box = document.getElementById("credBox");
  const icon = document.getElementById("credIcon");
  const title = document.getElementById("credTitle");
  const desc = document.getElementById("credDesc");

  if (!check || !check.checked) { box.hidden = true; return; }

  box.hidden = false;
  if (check.found) {
    box.className = "cred-box found";
    icon.textContent = "✓";
    const toolMatch = check.matches.find(m => m.type === "tool_hint");
    title.textContent = toolMatch ? `AI disclosure found — possibly ${toolMatch.matched}` : "AI disclosure metadata found";
    const uniqueFields = [...new Map(check.matches.map(m => [m.field + m.value, m])).values()];
    desc.textContent = "This file's own embedded metadata declares AI involvement — " +
      uniqueFields.map(m => `${m.field}: "${m.value}"`).join("; ") +
      ". This is a self-reported label from the export tool, not TRACE's own analysis.";
  } else {
    box.className = "cred-box not-found";
    icon.textContent = "–";
    title.textContent = "No embedded AI disclosure found";
    desc.textContent = "No Content-Credentials-style metadata was found in this file. This is normal and common — " +
      "most videos, including most manipulated ones, don't carry this metadata (it's easily stripped by re-encoding " +
      "or re-uploading). Absence here does not mean the video is real.";
  }
}

function setStatus(cls, text) {
  statusPill.className = "status-pill " + cls;
  statusPill.innerHTML = `<span class="dot"></span>${text}`;
}

let fakeProgressTimer = null;
function animateFakeProgress() {
  let pct = 5;
  const labels = ["Extracting frames…", "Detecting facial regions…", "Running ELA + noise-residual pass…", "Scoring frequency-domain artifacts…", "Extracting audio track…", "Building spectrogram…", "Combining signals…"];
  let li = 0;
  clearInterval(fakeProgressTimer);
  fakeProgressTimer = setInterval(() => {
    pct = Math.min(pct + Math.random() * 9, 94);
    progressFill.style.width = pct + "%";
    if (Math.random() > 0.6 && li < labels.length - 1) { li++; progressLabel.textContent = labels[li]; }
    if (pct >= 94) clearInterval(fakeProgressTimer);
  }, 380);
}

// ---------------- render results ----------------

function renderResults(data) {
  emptyState.hidden = true;
  readout.hidden = false;
  progressFill.style.width = "100%";

  const pct = data.alteration_pct;

  if (pct !== null && pct !== undefined) {
    animateGauge(pct, data.verdict);
  } else {
    gaugeScore.textContent = "N/A";
  }

  verdictLabel.textContent = data.verdict || "NO FACE FOUND";
  verdictLabel.className = "verdict-label " + (data.verdict === "FAKE" ? "fake" : "real");
  verdictDesc.textContent = data.explanation || "No face could be detected in the sampled frames — try a clip with a clearer, front-facing subject.";

  const techniqueBox = document.getElementById("techniqueBox");
  const techniqueLabel = document.getElementById("techniqueLabel");
  const techniqueDesc = document.getElementById("techniqueDesc");
  if (data.technique) {
    techniqueBox.hidden = false;
    techniqueLabel.textContent = data.technique.technique;
    techniqueDesc.textContent = data.technique.technique_desc;
  } else {
    techniqueBox.hidden = true;
  }

  const groqBox = document.getElementById("groqBox");
  const groqLabel = document.getElementById("groqLabel");
  const groqDesc = document.getElementById("groqDesc");
  if (data.groq_review && data.groq_review.enabled) {
    groqBox.hidden = false;
    groqLabel.textContent = `Groq AI review · ${data.groq_review.label || "UNCERTAIN"}`;
    const s = Math.round((data.groq_review.score || 0) * 100);
    groqDesc.textContent = `${s}% visual manipulation risk from the sampled frames. ${data.groq_review.summary || ""}`;
  } else {
    groqBox.hidden = true;
  }

  const reportBtn = document.getElementById("reportBtn");
  if (data.job_id) {
    reportBtn.hidden = false;
    reportBtn.onclick = () => window.open(`/api/report/${data.job_id}`, "_blank");
  } else {
    reportBtn.hidden = true;
  }

  renderCredentials(data.metadata_check);

  if (data.video_score !== null) {
    videoMeter.style.width = Math.round(data.video_score * 100) + "%";
    videoMeterVal.textContent = Math.round(data.video_score * 100) + "%";
  } else {
    videoMeter.style.width = "0%"; videoMeterVal.textContent = "n/a";
  }
  if (data.audio && data.audio.score !== undefined) {
    audioMeter.style.width = Math.round(data.audio.score * 100) + "%";
    audioMeterVal.textContent = Math.round(data.audio.score * 100) + "%";
  } else {
    audioMeter.style.width = "0%"; audioMeterVal.textContent = "no audio";
  }

  if (data.frames && data.frames.length > 0) {
    let maxI = 0;
    data.frames.forEach((f, i) => { if (f.score > data.frames[maxI].score) maxI = i; });
    selectedFrameIdx = maxI;
    renderFrame(data.frames[selectedFrameIdx]);
    drawTimeline(data.frames);
  } else {
    stageImg.removeAttribute("src");
    signalBars.innerHTML = "<p style='color:var(--muted);font-size:12.5px'>No frame-level data available.</p>";
  }

  if (data.audio) {
    audioStage.hidden = false;
    spectrogramImg.src = data.audio.spectrogram_image;
    audioSignals.innerHTML = "";
    const sig = data.audio.signals;
    [["Roll-off naturalness", sig.rolloff_naturalness], ["Discontinuity", sig.discontinuity], ["Spectral flatness", sig.spectral_flatness]].forEach(([label, val]) => {
      const el = document.createElement("span");
      el.className = "asig";
      el.innerHTML = `${label}: <b>${Math.round(val * 100)}%</b>`;
      audioSignals.appendChild(el);
    });
  } else {
    audioStage.hidden = true;
  }

  loadHistory();
}

let selectedFaceIdx = 0;

function renderFrame(frame) {
  stageImg.src = frame.image;
  selectedFaceIdx = frame.primary_face_index || 0;
  renderFacePanel(frame);
}

function renderFacePanel(frame) {
  const face = frame.faces[selectedFaceIdx];
  signalBars.innerHTML = "";

  if (frame.faces.length > 1) {
    const picker = document.createElement("div");
    picker.className = "face-picker";
    frame.faces.forEach((f, i) => {
      const btn = document.createElement("button");
      btn.className = "face-pill" + (i === selectedFaceIdx ? " active" : "");
      btn.textContent = `P${i + 1} · ${Math.round(f.score * 100)}%`;
      btn.onclick = () => { selectedFaceIdx = i; renderFacePanel(frame); };
      picker.appendChild(btn);
    });
    signalBars.appendChild(picker);
  }

  const items = [
    ["ELA", face.signals.ela, "#f5ab3d"],
    ["Noise residual", face.signals.noise_inconsistency, "#5093c9"],
    ["Frequency artifact", face.signals.frequency_artifact, "#c57fe0"],
    ["Boundary blend", face.signals.boundary_blend, "#35d692"],
  ];
  items.forEach(([label, val, color]) => {
    const row = document.createElement("div");
    row.className = "sbar-row";
    row.innerHTML = `
      <div class="sbar-label"><span>${label}</span><span>${Math.round(val * 100)}%</span></div>
      <div class="sbar-track"><div class="sbar-fill" style="width:${Math.round(val*100)}%;background:${color}"></div></div>
    `;
    signalBars.appendChild(row);
  });
  const meta = document.createElement("p");
  meta.style.cssText = "font-family:var(--mono);font-size:11px;color:var(--muted-2);margin-top:16px;";
  const personLabel = frame.faces.length > 1 ? `person ${selectedFaceIdx + 1} of ${frame.faces.length} — ` : "";
  meta.textContent = `${personLabel}frame @ ${frame.timestamp}s — ${Math.round(face.score * 100)}% altered`;
  signalBars.appendChild(meta);
}

function drawTimeline(frames) {
  const ctx = timelineCanvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = timelineCanvas.parentElement.clientWidth;
  const cssHeight = 46;
  timelineCanvas.width = cssWidth * dpr;
  timelineCanvas.height = cssHeight * dpr;
  timelineCanvas.style.width = cssWidth + "px";
  timelineCanvas.style.height = cssHeight + "px";
  ctx.scale(dpr, dpr);
  const n = frames.length;
  const barW = cssWidth / n;

  function paint(hoverIdx) {
    ctx.clearRect(0, 0, cssWidth, cssHeight);
    frames.forEach((f, i) => {
      const h = Math.max(3, f.score * (cssHeight - 6));
      const x = i * barW, y = cssHeight - h;
      const isSel = i === selectedFrameIdx;
      ctx.fillStyle = f.score >= 0.42 ? "#ef5257" : "#5093c9";
      ctx.globalAlpha = isSel ? 1 : (hoverIdx === i ? 0.85 : 0.55);
      ctx.fillRect(x + 1, y, Math.max(1, barW - 2), h);
    });
    ctx.globalAlpha = 1;
  }
  paint(-1);
  timelineCanvas.onmousemove = e => {
    const rect = timelineCanvas.getBoundingClientRect();
    const idx = Math.min(n - 1, Math.max(0, Math.floor((e.clientX - rect.left) / barW)));
    paint(idx);
  };
  timelineCanvas.onmouseleave = () => paint(-1);
  timelineCanvas.onclick = e => {
    const rect = timelineCanvas.getBoundingClientRect();
    const idx = Math.min(n - 1, Math.max(0, Math.floor((e.clientX - rect.left) / barW)));
    selectedFrameIdx = idx;
    renderFrame(frames[idx]);
    paint(idx);
  };
}

window.addEventListener("resize", () => { if (lastPayload && lastPayload.frames && lastPayload.frames.length) drawTimeline(lastPayload.frames); });

// ---------------- history drawer ----------------

const historyBtn = document.getElementById("historyBtn");
const historyDrawer = document.getElementById("historyDrawer");
const drawerOverlay = document.getElementById("drawerOverlay");
const drawerClose = document.getElementById("drawerClose");
const historyList = document.getElementById("historyList");
const historyEmpty = document.getElementById("historyEmpty");

function openDrawer() { historyDrawer.classList.add("open"); drawerOverlay.classList.add("open"); loadHistory(); }
function closeDrawer() { historyDrawer.classList.remove("open"); drawerOverlay.classList.remove("open"); }
historyBtn.addEventListener("click", openDrawer);
drawerClose.addEventListener("click", closeDrawer);
drawerOverlay.addEventListener("click", closeDrawer);

async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    const items = await res.json();
    renderHistory(items);
  } catch (err) { console.error("Failed to load history", err); }
}

function renderHistory(items) {
  historyList.querySelectorAll(".history-item").forEach(el => el.remove());
  if (!items || items.length === 0) { historyEmpty.style.display = "block"; return; }
  historyEmpty.style.display = "none";
  items.forEach(item => {
    const confPct = item.confidence !== null && item.confidence !== undefined ? Math.round(item.confidence * 100) : null;
    const when = new Date(item.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    const el = document.createElement("div");
    el.className = "history-item";
    el.innerHTML = `
      <img class="history-thumb" src="${item.thumbnail || ''}" onerror="this.style.visibility='hidden'">
      <div class="history-meta">
        <p class="history-filename">${escapeHtml(item.filename || 'clip')}</p>
        <div class="history-badges">
          <span class="history-verdict ${item.verdict || ''}">${item.verdict || 'N/A'}${confPct !== null ? ' · ' + confPct + '%' : ''}</span>
        </div>
        <span class="history-time">${when}</span>
      </div>
    `;
    el.addEventListener("click", () => loadHistoryItem(item.job_id));
    historyList.appendChild(el);
  });
}

async function loadHistoryItem(jobId) {
  try {
    const res = await fetch(`/api/history/${jobId}`);
    const data = await res.json();
    lastPayload = data;
    renderResults(data);
    closeDrawer();
    setStatus(data.verdict === "FAKE" ? "fake" : "done", data.verdict ? data.verdict.toLowerCase() : "complete");
  } catch (err) { console.error("Failed to load history item", err); }
}

loadHistory();

document.getElementById("logoutBtn").addEventListener("click", async () => {
  try { await fetch("/api/logout", { method: "POST" }); } catch (e) {}
  window.location.href = "/login";
});

// ---------------- chat widget ----------------

const chatFab = document.getElementById("chatFab");
const chatPanel = document.getElementById("chatPanel");
const chatClose = document.getElementById("chatClose");
const chatMessages = document.getElementById("chatMessages");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");

let chatHistory = [];

chatFab.addEventListener("click", () => { chatPanel.classList.add("open"); chatFab.classList.add("hide"); chatInput.focus(); });
chatClose.addEventListener("click", () => { chatPanel.classList.remove("open"); chatFab.classList.remove("hide"); });

chatForm.addEventListener("submit", async e => {
  e.preventDefault();
  const msg = chatInput.value.trim();
  if (!msg) return;
  appendMsg(msg, "user");
  chatHistory.push({ role: "user", content: msg });
  chatInput.value = "";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg, history: chatHistory }),
    });
    const data = await res.json();
    appendMsg(data.reply, "bot");
    chatHistory.push({ role: "assistant", content: data.reply });
  } catch (err) {
    appendMsg("Sorry, something went wrong reaching the assistant.", "bot");
  }
});

function appendMsg(text, who) {
  const el = document.createElement("div");
  el.className = "msg msg-" + who;
  el.textContent = text;
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ---------------- bookmarklet ----------------

(function setupBookmarklet() {
  const link = document.getElementById("bookmarkletLink");
  if (!link) return;
  const origin = window.location.origin;
  const code = `javascript:(function(){window.open('${origin}/?scan_url='+encodeURIComponent(window.location.href),'_blank');})();`;
  link.setAttribute("href", code);
})();

// ---------------- auto-scan from bookmarklet / shared link ----------------

(function autoScanFromQuery() {
  const params = new URLSearchParams(window.location.search);
  const scanUrl = params.get("scan_url");
  if (!scanUrl) return;
  urlInput.value = scanUrl;
  window.history.replaceState({}, "", window.location.pathname);
  runUrlAnalysis();
})();

// resume polling if a scan was left running (e.g. page was refreshed or reopened)
// placed at the very end so all `let`/`const` declarations above have run first
(function resumePendingJob() {
  const pending = localStorage.getItem(PENDING_JOB_KEY);
  if (pending) pollJob(pending, analyzeBtn);
})();
