const transcriptFileInput = document.getElementById("transcriptFile");
const transcriptTextArea = document.getElementById("transcriptText");
const suggestBtn = document.getElementById("suggestBtn");
const statusPill = document.getElementById("statusPill");
const courseTitle1 = document.getElementById("courseTitle1");
const courseTitle2 = document.getElementById("courseTitle2");
const courseTitle3 = document.getElementById("courseTitle3");
const courseReason1 = document.getElementById("courseReason1");
const courseReason2 = document.getElementById("courseReason2");
const courseReason3 = document.getElementById("courseReason3");
const summaryText = document.getElementById("summaryText");
const errorText = document.getElementById("errorText");
const resultsActions = document.getElementById("resultsActions");
const courseGrid = document.getElementById("courseGrid");
const summaryCard = document.getElementById("summaryCard");
const resultLoading = document.getElementById("resultLoading");
const errorCard = document.getElementById("errorCard");
const startBtn = document.getElementById("startBtn");
const dotHistory = document.getElementById("dotHistory");
const backToIntroBtn = document.getElementById("backToIntroBtn");
const backFromHistoryBtn = document.getElementById("backFromHistoryBtn");
const continueNewBtn = document.getElementById("continueNewBtn");
const reviseBtn = document.getElementById("reviseBtn");
const restartBtn = document.getElementById("restartBtn");
const historyList = document.getElementById("historyList");
const historyEmptyHint = document.getElementById("historyEmptyHint");
const historyEmptyQuarter = document.getElementById("historyEmptyQuarter");
const historyQuarterBar = document.getElementById("historyQuarterBar");
const historyQuarterSelect = document.getElementById("historyQuarterSelect");
const planQuarterSelect = document.getElementById("planQuarterSelect");
const historyStatus = document.getElementById("historyStatus");
const savePrompt = document.getElementById("savePrompt");
const saveOutputBtn = document.getElementById("saveOutputBtn");
const saveStatus = document.getElementById("saveStatus");
const resetAllDataBtn = document.getElementById("resetAllDataBtn");
const backupDataBtn = document.getElementById("backupDataBtn");
const restoreDataBtn = document.getElementById("restoreDataBtn");
const restoreDataFile = document.getElementById("restoreDataFile");
const screenIntro = document.getElementById("screenIntro");
const screenHistory = document.getElementById("screenHistory");
const screenInput = document.getElementById("screenInput");
const screenResults = document.getElementById("screenResults");
const screenPlan = document.getElementById("screenPlan");
const fourYearTableBody = document.getElementById("fourYearTableBody");
const navPlanBtn = document.getElementById("navPlanBtn");
const openFourYearBtn = document.getElementById("openFourYearBtn");
const backFromPlanBtn = document.getElementById("backFromPlanBtn");
const planImportOpenBtn = document.getElementById("planImportOpenBtn");
const planImportModal = document.getElementById("planImportModal");
const planImportBackdrop = document.getElementById("planImportBackdrop");
const planImportSelect = document.getElementById("planImportSelect");
const planImportTargetSelect = document.getElementById("planImportTargetSelect");
const planImportPreview = document.getElementById("planImportPreview");
const planImportCancelBtn = document.getElementById("planImportCancelBtn");
const planImportApplyBtn = document.getElementById("planImportApplyBtn");
const historyToPlanBtn = document.getElementById("historyToPlanBtn");
const planGraduationYearSelect = document.getElementById("planGraduationYear");
const planIncludeSummerToggle = document.getElementById("planIncludeSummerToggle");
const planChatQuestion = document.getElementById("planChatQuestion");
const planChatSendBtn = document.getElementById("planChatSendBtn");
const planChatStatus = document.getElementById("planChatStatus");
const planChatError = document.getElementById("planChatError");
const planChatReplyWrap = document.getElementById("planChatReplyWrap");
const planChatReply = document.getElementById("planChatReply");
const dotIntro = document.getElementById("dotIntro");
const dotInput = document.getElementById("dotInput");
const dotResults = document.getElementById("dotResults");
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ALLOWED_MIME_TYPES = new Set(["application/pdf", "image/jpeg", "text/plain"]);
const SEASON_ORDER = { Fall: 0, Winter: 1, Spring: 2 };
const QUARTER_KEY_RE = /^(\d{4})-(Fall|Winter|Spring)$/;
/** History filter: show every saved plan regardless of quarter. */
const HISTORY_QUARTER_ALL = "__all_terms__";
const FOUR_YEAR_STORAGE_KEY = "scu-course-planner-four-year-v1";
const BACKUP_FORMAT_VERSION = 1;
const PLAN_YEARS = [
  { id: "freshman", label: "Freshman" },
  { id: "sophomore", label: "Sophomore" },
  { id: "junior", label: "Junior" },
  { id: "senior", label: "Senior" }
];
const PLAN_QUARTERS = [
  { id: "fall", label: "Fall" },
  { id: "winter", label: "Winter" },
  { id: "spring", label: "Spring" },
  { id: "summer", label: "Summer" }
];

let selectedFilePayload = null;
let lastSuccessfulResult = null;
let savedEntries = [];
let historyMutationLock = false;
let historyViewQuarterKey = "";
let fourYearListenersBound = false;

function dateToCurrentQuarter(d) {
  const m = d.getMonth();
  const y = d.getFullYear();
  if (m >= 8) return { season: "Fall", year: y };
  if (m <= 2) return { season: "Winter", year: y };
  if (m <= 5) return { season: "Spring", year: y };
  return { season: "Fall", year: y };
}

function followingQuarter(q) {
  if (q.season === "Fall") return { season: "Winter", year: q.year + 1 };
  if (q.season === "Winter") return { season: "Spring", year: q.year };
  return { season: "Fall", year: q.year };
}

function formatQuarterKey(q) {
  return `${q.year}-${q.season}`;
}

function parseQuarterKey(key) {
  const m = QUARTER_KEY_RE.exec(key);
  if (!m) return null;
  return { year: Number(m[1]), season: m[2] };
}

function quarterSortIndex(q) {
  if (!q) return 0;
  const ay = q.season === "Fall" ? q.year : q.year - 1;
  return ay * 3 + SEASON_ORDER[q.season];
}

function compareQuarterKeys(a, b) {
  return quarterSortIndex(parseQuarterKey(a)) - quarterSortIndex(parseQuarterKey(b));
}

function labelQuarterKey(key) {
  const q = parseQuarterKey(key);
  return q ? `${q.season} ${q.year}` : key;
}

function stepQuarter(q, steps) {
  let cur = { ...q };
  for (let s = 0; s < steps; s++) cur = followingQuarter(cur);
  return cur;
}

function normalizeEntryQuarter(entry) {
  if (!entry) return "";
  const q = entry.quarter;
  if (typeof q === "string" && QUARTER_KEY_RE.test(q)) return q;
  return formatQuarterKey(dateToCurrentQuarter(new Date(entry.savedAt || Date.now())));
}

function collectQuarterKeysFromEntries(entries) {
  return [...new Set(entries.map(normalizeEntryQuarter).filter(Boolean))];
}

function pickDefaultHistoryQuarter(entries) {
  const keys = collectQuarterKeysFromEntries(entries);
  if (keys.length === 0) return "";
  const following = formatQuarterKey(followingQuarter(dateToCurrentQuarter(new Date())));
  if (keys.includes(following)) return following;
  const sorted = [...keys].sort(compareQuarterKeys);
  const fk = quarterSortIndex(parseQuarterKey(following));
  const idx = sorted.findIndex((k) => quarterSortIndex(parseQuarterKey(k)) >= fk);
  if (idx >= 0) return sorted[idx];
  return sorted[sorted.length - 1];
}

function fillPlanQuarterSelect() {
  if (!planQuarterSelect) return;
  const start = followingQuarter(dateToCurrentQuarter(new Date()));
  planQuarterSelect.innerHTML = "";
  for (let i = 0; i < 5; i++) {
    const key = formatQuarterKey(stepQuarter(start, i));
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = labelQuarterKey(key);
    planQuarterSelect.appendChild(opt);
  }
  planQuarterSelect.selectedIndex = 0;
}

function refreshHistoryQuarterDropdown() {
  if (!historyQuarterSelect) return;
  const keys = collectQuarterKeysFromEntries(savedEntries).sort(compareQuarterKeys);
  historyQuarterSelect.innerHTML = "";
  if (savedEntries.length > 0) {
    const allOpt = document.createElement("option");
    allOpt.value = HISTORY_QUARTER_ALL;
    allOpt.textContent = "All terms";
    historyQuarterSelect.appendChild(allOpt);
  }
  for (const key of keys) {
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = labelQuarterKey(key);
    historyQuarterSelect.appendChild(opt);
  }
  if (historyQuarterBar) {
    historyQuarterBar.classList.toggle("hidden", savedEntries.length === 0);
  }
}

function applyHistoryQuarterSelection() {
  if (!historyQuarterSelect) return;
  if (savedEntries.length === 0) return;
  const keys = collectQuarterKeysFromEntries(savedEntries).sort(compareQuarterKeys);
  const valid = new Set([HISTORY_QUARTER_ALL, ...keys]);
  if (!valid.has(historyViewQuarterKey)) {
    historyViewQuarterKey = pickDefaultHistoryQuarter(savedEntries);
    if (!valid.has(historyViewQuarterKey)) {
      historyViewQuarterKey = HISTORY_QUARTER_ALL;
    }
  }
  historyQuarterSelect.value = historyViewQuarterKey;
}

function setHistoryStatus(message, isError = true) {
  if (!historyStatus) return;
  historyStatus.textContent = message || "";
  if (!message) {
    historyStatus.style.color = "";
    return;
  }
  historyStatus.style.color = isError ? "#ffb4a8" : "#a8e0c0";
}

function updateHistoryNavAvailability() {
  if (!dotHistory) return;
  const hasAny = Array.isArray(savedEntries) && savedEntries.length > 0;
  dotHistory.disabled = !hasAny;
  dotHistory.classList.toggle("dot--disabled", !hasAny);
  dotHistory.title = hasAny ? "" : "History is empty — save an output first";
  dotHistory.setAttribute(
    "aria-label",
    hasAny ? "History" : "History (disabled — no saved plans yet)"
  );
}

function captureHistoryRowRects() {
  const map = new Map();
  if (!historyList) return map;
  historyList.querySelectorAll(".history-row").forEach((row) => {
    const id = row.dataset.entryId;
    if (id) map.set(id, row.getBoundingClientRect());
  });
  return map;
}

function animateHistoryReorder(prevRects) {
  if (!prevRects || prevRects.size === 0 || !historyList) return;
  const rows = [...historyList.querySelectorAll(".history-row")];
  const moving = new Map();
  for (const row of rows) {
    const id = row.dataset.entryId;
    if (!id || !prevRects.has(id)) continue;
    const before = prevRects.get(id);
    const after = row.getBoundingClientRect();
    const dy = before.top - after.top;
    if (Math.abs(dy) > 0.5) moving.set(row, dy);
  }
  if (moving.size === 0) return;

  for (const [row, dy] of moving) {
    row.classList.add("history-row--reorder");
    row.style.transform = `translateY(${dy}px)`;
    row.style.transition = "none";
  }
  historyList.offsetHeight;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      for (const row of moving.keys()) {
        row.style.transition = "transform 0.48s cubic-bezier(0.22, 1.32, 0.36, 1)";
        row.style.transform = "translateY(0)";
      }
      window.setTimeout(() => {
        for (const row of moving.keys()) {
          row.classList.remove("history-row--reorder");
          row.style.transition = "";
          row.style.transform = "";
        }
      }, 520);
    });
  });
}

transcriptFileInput.addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) {
    selectedFilePayload = null;
    return;
  }

  const normalizedType = (file.type || "").toLowerCase();
  const looksLikeTxt = file.name.toLowerCase().endsWith(".txt");
  const mimeType = normalizedType || (looksLikeTxt ? "text/plain" : "");
  if (!ALLOWED_MIME_TYPES.has(mimeType)) {
    selectedFilePayload = null;
    transcriptFileInput.value = "";
    statusPill.textContent = "Upload JPG, PDF, or TXT only";
    return;
  }

  if (file.size > MAX_UPLOAD_BYTES) {
    selectedFilePayload = null;
    transcriptFileInput.value = "";
    statusPill.textContent = "File must be under 10MB";
    return;
  }

  const dataBase64 = await fileToGeminiBase64(file, mimeType);
  selectedFilePayload = {
    fileName: file.name,
    mimeType,
    dataBase64
  };
  statusPill.textContent = `Loaded ${file.name}`;
});

suggestBtn.addEventListener("click", async () => {
  const transcriptText = transcriptTextArea.value.trim();
  if (!transcriptText && !selectedFilePayload) {
    statusPill.textContent = "Add text or upload a file first";
    return;
  }

  suggestBtn.disabled = true;
  lastSuccessfulResult = null;
  showScreen("results");
  setActionsVisible(false);
  setErrorMode(false);
  statusPill.textContent = "Generating recommendation...";
  setResultsVisible(false);
  setLoadingVisible(true);
  setLoadingState();

  try {
    const response = await fetch("/api/suggest-courses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transcriptText,
        file: selectedFilePayload
      })
    });

    const data = await response.json();

    if (!response.ok) {
      statusPill.textContent = "Error";
      renderError(data.details ? `${data.error}\n\n${data.details}` : data.error || "Request failed");
      return;
    }

    const recommendations = Array.isArray(data.recommendations) ? data.recommendations.slice(0, 3) : [];
    const summary = typeof data.summary === "string" ? data.summary.trim() : "";
    if (recommendations.length < 3 || !summary) {
      statusPill.textContent = "No suggestion returned";
      renderError("Gemini did not return the expected top-3 course format. Try again.");
      return;
    }

    statusPill.textContent = "Suggestion generated";
    renderStructuredResult(recommendations, summary);
  } catch (error) {
    statusPill.textContent = "Error";
    renderError(error.message);
  } finally {
    setLoadingVisible(false);
    setResultsVisible(true);
    suggestBtn.disabled = false;
    setActionsVisible(true);
  }
});

backToIntroBtn.addEventListener("click", () => showScreen("intro"));
backFromHistoryBtn.addEventListener("click", () => showScreen("intro"));
continueNewBtn.addEventListener("click", () => {
  fillPlanQuarterSelect();
  showScreen("input");
});
reviseBtn.addEventListener("click", () => {
  fillPlanQuarterSelect();
  showScreen("input");
});
restartBtn.addEventListener("click", () => {
  transcriptFileInput.value = "";
  transcriptTextArea.value = "";
  clearResultCards();
  selectedFilePayload = null;
  statusPill.textContent = "Idle";
  setLoadingVisible(false);
  setResultsVisible(true);
  setActionsVisible(false);
  setSavePromptVisible(false);
  showScreen("intro");
});

async function openHistoryOrInputFromGate() {
  setHistoryStatus("");
  await loadSavedEntries();
  updateHistoryNavAvailability();
  fillPlanQuarterSelect();
  if (savedEntries.length > 0) {
    historyViewQuarterKey = pickDefaultHistoryQuarter(savedEntries);
    refreshHistoryQuarterDropdown();
    applyHistoryQuarterSelection();
    renderHistoryList();
    showScreen("history");
  } else {
    showScreen("input");
  }
}

startBtn.addEventListener("click", () => {
  openHistoryOrInputFromGate();
});

if (dotIntro) {
  dotIntro.addEventListener("click", () => showScreen("intro"));
}

if (dotHistory) {
  dotHistory.addEventListener("click", () => {
    openHistoryOrInputFromGate();
  });
}

if (dotInput) {
  dotInput.addEventListener("click", () => {
    fillPlanQuarterSelect();
    showScreen("input");
  });
}

if (historyQuarterSelect) {
  historyQuarterSelect.addEventListener("change", () => {
    historyViewQuarterKey = historyQuarterSelect.value;
    renderHistoryList();
  });
}

resetAllDataBtn.addEventListener("click", async () => {
  const ok = window.confirm(
    "Clear all saved plans on the server and remove site data from this browser (local storage, session storage, and non-HttpOnly cookies on this origin)?"
  );
  if (!ok) return;
  try {
    localStorage.clear();
    sessionStorage.clear();
  } catch {
    /* ignore */
  }
  try {
    document.cookie.split(";").forEach((cookie) => {
      const name = cookie.split("=")[0].trim();
      if (name) {
        document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/`;
      }
    });
  } catch {
    /* ignore */
  }
  try {
    const response = await fetch("/api/saved-outputs", { method: "DELETE" });
    if (!response.ok) {
      window.alert("Could not clear saved plans on the server. Check that the app is running.");
      return;
    }
  } catch {
    window.alert("Could not reach the server to clear saved plans.");
    return;
  }
  savedEntries = [];
  updateHistoryNavAvailability();
  historyViewQuarterKey = "";
  refreshHistoryQuarterDropdown();
  renderHistoryList();
  showScreen("intro");
  window.alert("All saved outputs and browser storage for this app have been cleared.");
});

function downloadJsonFile(fileName, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

async function createBackupPayload() {
  let fourYearRaw = null;
  try {
    fourYearRaw = localStorage.getItem(FOUR_YEAR_STORAGE_KEY);
  } catch {
    fourYearRaw = null;
  }

  let savedOutputs = null;
  try {
    const response = await fetch("/api/saved-outputs");
    const data = await response.json();
    if (response.ok) {
      savedOutputs = Array.isArray(data.entries) ? data.entries : [];
    }
  } catch {
    savedOutputs = null;
  }

  return {
    format: "scu-course-planner-backup",
    version: BACKUP_FORMAT_VERSION,
    exportedAt: new Date().toISOString(),
    origin: typeof window !== "undefined" ? window.location.origin : "",
    fourYear: fourYearRaw,
    savedOutputs
  };
}

function parseBackupJson(text) {
  const data = JSON.parse(text);
  if (!data || typeof data !== "object") throw new Error("Backup file is not valid JSON.");
  if (data.format !== "scu-course-planner-backup") {
    throw new Error("Not a SCU Course Planner backup file.");
  }
  return data;
}

async function restoreFromBackupPayload(payload) {
  const ok = window.confirm(
    "Restore will overwrite this browser’s four-year grid and replace the server’s saved plans with the backup. Continue?"
  );
  if (!ok) return;

  // Restore browser-only grid first (safe even if server is unavailable).
  if (typeof payload.fourYear === "string") {
    try {
      localStorage.setItem(FOUR_YEAR_STORAGE_KEY, payload.fourYear);
    } catch {
      /* ignore quota / blocked */
    }
  }

  // Restore server saved outputs (requires app running via http://localhost..., not file://).
  if (Array.isArray(payload.savedOutputs)) {
    try {
      const del = await fetch("/api/saved-outputs", { method: "DELETE" });
      if (!del.ok) throw new Error("Could not clear server saved outputs.");

      // POST unshifts, so insert from oldest -> newest to preserve list order.
      const entries = payload.savedOutputs.slice().reverse();
      for (const entry of entries) {
        await fetch("/api/saved-outputs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            recommendations: entry.recommendations,
            summary: entry.summary,
            quarter: entry.quarter
          })
        });
      }
    } catch (err) {
      window.alert(
        `Restored the four-year grid locally, but could not restore saved plans to the server.\n\n${err.message || err}`
      );
    }
  }

  await loadSavedEntries();
  refreshHistoryQuarterDropdown();
  applyHistoryQuarterSelection();
  renderHistoryList();
  if (document.body.dataset.ambient === "plan") {
    loadFourYearFromStorage();
  }
  window.alert("Restore complete.");
}

if (backupDataBtn) {
  backupDataBtn.addEventListener("click", async () => {
    backupDataBtn.disabled = true;
    try {
      const payload = await createBackupPayload();
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      downloadJsonFile(`scu-course-planner-backup-${stamp}.json`, payload);
    } catch (err) {
      window.alert(err.message || "Could not create backup.");
    } finally {
      backupDataBtn.disabled = false;
    }
  });
}

if (restoreDataBtn && restoreDataFile) {
  restoreDataBtn.addEventListener("click", () => {
    restoreDataFile.value = "";
    restoreDataFile.click();
  });
  restoreDataFile.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const payload = parseBackupJson(text);
      await restoreFromBackupPayload(payload);
    } catch (err) {
      window.alert(err.message || "Could not restore from that file.");
    } finally {
      restoreDataFile.value = "";
    }
  });
}

saveOutputBtn.addEventListener("click", async () => {
  if (!lastSuccessfulResult) return;
  saveOutputBtn.disabled = true;
  saveStatus.textContent = "Saving...";
  try {
    const response = await fetch("/api/saved-outputs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recommendations: lastSuccessfulResult.recommendations,
        summary: lastSuccessfulResult.summary,
        quarter: lastSuccessfulResult.quarter || planQuarterSelect?.value
      })
    });
    const data = await response.json();
    if (!response.ok) {
      saveStatus.textContent = data.error || "Save failed.";
      return;
    }
    saveStatus.textContent = "Saved.";
    await loadSavedEntries();
  } catch {
    saveStatus.textContent = "Save failed.";
  } finally {
    saveOutputBtn.disabled = false;
  }
});

function renderError(message) {
  setSavePromptVisible(false);
  setErrorMode(true);
  errorText.textContent = `${message}\n\nAdjust your input and try generating recommendations again.`;
}

function renderStructuredResult(recommendations, summary, options = {}) {
  const quarterOverride = options.quarterOverride;
  const quarter =
    typeof quarterOverride === "string" && QUARTER_KEY_RE.test(quarterOverride)
      ? quarterOverride
      : planQuarterSelect?.value || "";
  lastSuccessfulResult = { recommendations, summary, quarter };
  if (!options.suppressSavePrompt) {
    setSavePromptVisible(true);
  }
  saveStatus.textContent = "";
  setErrorMode(false);
  const [r1, r2, r3] = recommendations;
  courseTitle1.textContent = r1.course || "Course unavailable";
  courseTitle2.textContent = r2.course || "Course unavailable";
  courseTitle3.textContent = r3.course || "Course unavailable";
  courseReason1.textContent = r1.reason || "No reason provided.";
  courseReason2.textContent = r2.reason || "No reason provided.";
  courseReason3.textContent = r3.reason || "No reason provided.";
  summaryText.textContent = summary;
}

function clearResultCards() {
  courseTitle1.textContent = "-";
  courseTitle2.textContent = "-";
  courseTitle3.textContent = "-";
  courseReason1.textContent = "";
  courseReason2.textContent = "";
  courseReason3.textContent = "";
  summaryText.textContent = "";
  errorText.textContent = "";
  saveStatus.textContent = "";
}

function setLoadingState() {
  courseTitle1.textContent = "Analyzing transcript...";
  courseTitle2.textContent = "Checking prerequisites...";
  courseTitle3.textContent = "Balancing workload...";
  courseReason1.textContent = "";
  courseReason2.textContent = "";
  courseReason3.textContent = "";
  summaryText.textContent = "Generating your top 3 recommendations...";
}

function setActionsVisible(visible) {
  resultsActions.classList.toggle("hidden", !visible);
}

function setLoadingVisible(visible) {
  screenResults.classList.toggle("loading", visible);
  resultLoading.classList.toggle("hidden", !visible);
}

function setResultsVisible(visible) {
  courseGrid.classList.toggle("hidden", !visible);
  summaryCard.classList.toggle("hidden", !visible);
  if (!visible) {
    errorCard.classList.add("hidden");
  }
}

function setErrorMode(visible) {
  errorCard.classList.toggle("hidden", !visible);
  courseGrid.classList.toggle("hidden", visible);
  summaryCard.classList.toggle("hidden", visible);
}

function setSavePromptVisible(visible) {
  savePrompt.classList.toggle("hidden", !visible);
}

async function loadSavedEntries() {
  try {
    const response = await fetch("/api/saved-outputs");
    const data = await response.json();
    if (!response.ok) {
      savedEntries = [];
      updateHistoryNavAvailability();
      return;
    }
    savedEntries = Array.isArray(data.entries) ? data.entries : [];
    updateHistoryNavAvailability();
  } catch {
    savedEntries = [];
    updateHistoryNavAvailability();
  }
}

function getFilteredHistoryEntries() {
  if (!historyViewQuarterKey) return [];
  if (historyViewQuarterKey === HISTORY_QUARTER_ALL) return [...savedEntries];
  return savedEntries.filter((e) => normalizeEntryQuarter(e) === historyViewQuarterKey);
}

function renderHistoryList() {
  historyList.innerHTML = "";
  const filtered = getFilteredHistoryEntries();
  historyEmptyHint.classList.toggle("hidden", savedEntries.length > 0);
  historyEmptyQuarter.classList.toggle(
    "hidden",
    savedEntries.length === 0 || filtered.length > 0
  );
  const allTermsView = historyViewQuarterKey === HISTORY_QUARTER_ALL;
  filtered.forEach((entry, index) => {
    const entryId = String(entry.id);
    const row = document.createElement("div");
    row.className = "history-row";
    row.dataset.entryId = entryId;

    const reorder = document.createElement("div");
    reorder.className = "history-reorder" + (allTermsView ? " history-reorder--disabled" : "");

    const upBtn = document.createElement("button");
    upBtn.type = "button";
    const atTop = index === 0;
    upBtn.className = "icon-btn" + (!allTermsView && atTop ? " icon-btn--edge" : "");
    upBtn.setAttribute(
      "aria-label",
      allTermsView
        ? "Reorder: choose a single quarter in the menu first"
        : atTop
          ? "Move up — already first"
          : "Move up"
    );
    upBtn.textContent = "↑";
    upBtn.disabled = historyMutationLock || allTermsView;

    const downBtn = document.createElement("button");
    downBtn.type = "button";
    const atBottom = index === filtered.length - 1;
    downBtn.className =
      "icon-btn" + (!allTermsView && atBottom ? " icon-btn--edge" : "");
    downBtn.setAttribute(
      "aria-label",
      allTermsView
        ? "Reorder: choose a single quarter in the menu first"
        : atBottom
          ? "Move down — already last"
          : "Move down"
    );
    downBtn.textContent = "↓";
    downBtn.disabled = historyMutationLock || allTermsView;

    upBtn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      moveHistoryEntryById(entryId, -1);
    });
    downBtn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      moveHistoryEntryById(entryId, 1);
    });

    reorder.appendChild(upBtn);
    reorder.appendChild(downBtn);

    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.className = "history-open";
    const headline = entry.recommendations?.map((r) => r.course).slice(0, 3).join(" | ");
    const date = new Date(entry.savedAt).toLocaleString();
    openBtn.innerHTML = `<strong>${escapeHtml(headline || "Saved recommendation")}</strong><span>${escapeHtml(date)}</span>`;
    openBtn.addEventListener("click", (event) => {
      event.preventDefault();
      setSavePromptVisible(false);
      showScreen("results");
      setLoadingVisible(false);
      setResultsVisible(true);
      setErrorMode(false);
      setActionsVisible(true);
      const qk = normalizeEntryQuarter(entry);
      statusPill.textContent = qk
        ? `Loaded saved plan (${labelQuarterKey(qk)})`
        : "Loaded saved recommendation";
      renderStructuredResult(entry.recommendations || [], entry.summary || "", {
        quarterOverride: qk,
        suppressSavePrompt: true
      });
    });

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "icon-btn danger";
    delBtn.setAttribute("aria-label", "Delete saved plan");
    delBtn.textContent = "×";
    delBtn.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!window.confirm("Delete this saved plan?")) return;
      await deleteHistoryEntry(entryId);
    });

    row.appendChild(reorder);
    row.appendChild(openBtn);
    row.appendChild(delBtn);
    historyList.appendChild(row);
  });
}

function nudgeHistoryRowEdge(entryId, delta) {
  if (!historyList || historyMutationLock) return;
  const row = [...historyList.querySelectorAll(".history-row")].find(
    (r) => r.dataset.entryId === String(entryId)
  );
  if (!row) return;

  row.classList.remove(
    "history-row--reorder",
    "history-row--edge-nudge-up",
    "history-row--edge-nudge-down"
  );
  row.style.transition = "";
  row.style.transform = "";
  row.offsetWidth;

  const cls = delta < 0 ? "history-row--edge-nudge-up" : "history-row--edge-nudge-down";
  row.classList.add(cls);

  const finish = (event) => {
    if (!event.animationName || !event.animationName.startsWith("history-edge-nudge")) return;
    row.classList.remove("history-row--edge-nudge-up", "history-row--edge-nudge-down");
    row.removeEventListener("animationend", finish);
  };
  row.addEventListener("animationend", finish);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function moveHistoryEntryById(entryId, delta) {
  if (historyMutationLock) return;
  if (historyViewQuarterKey === HISTORY_QUARTER_ALL) {
    setHistoryStatus("Pick one quarter in the menu to reorder plans for that term.");
    return;
  }
  if (!historyViewQuarterKey || !QUARTER_KEY_RE.test(historyViewQuarterKey)) {
    setHistoryStatus("Pick a quarter to reorder plans.");
    return;
  }
  const filtered = getFilteredHistoryEntries();
  const index = filtered.findIndex((e) => String(e.id) === String(entryId));
  if (index < 0) {
    setHistoryStatus("Could not find that entry. Refresh and try again.");
    return;
  }
  const nextIndex = index + delta;
  if (nextIndex < 0 || nextIndex >= filtered.length) {
    nudgeHistoryRowEdge(entryId, delta);
    return;
  }

  const reordered = [...filtered];
  const temp = reordered[index];
  reordered[index] = reordered[nextIndex];
  reordered[nextIndex] = temp;
  const order = reordered.map((e) => String(e.id));

  const prevRects = captureHistoryRowRects();
  historyMutationLock = true;
  setHistoryStatus("");
  let reorderOk = false;
  try {
    const response = await fetch("/api/saved-outputs/reorder", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quarter: historyViewQuarterKey, order })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setHistoryStatus(data.error || `Reorder failed (${response.status}).`);
      return;
    }
    await loadSavedEntries();
    reorderOk = true;
  } catch (err) {
    setHistoryStatus(err.message || "Network error while reordering.");
  } finally {
    historyMutationLock = false;
    renderHistoryList();
    if (reorderOk) animateHistoryReorder(prevRects);
  }
}

async function deleteHistoryEntry(id) {
  if (historyMutationLock) return;
  const sid = String(id);
  historyMutationLock = true;
  setHistoryStatus("");
  try {
    const response = await fetch(`/api/saved-outputs/${encodeURIComponent(sid)}`, {
      method: "DELETE"
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setHistoryStatus(data.error || `Delete failed (${response.status}).`);
      return;
    }
    await loadSavedEntries();
    setHistoryStatus("");
  } catch (err) {
    setHistoryStatus(err.message || "Network error while deleting.");
  } finally {
    historyMutationLock = false;
    refreshHistoryQuarterDropdown();
    applyHistoryQuarterSelection();
    renderHistoryList();
  }
}

async function fileToBase64(file) {
  const arrayBuffer = await file.arrayBuffer();
  let binary = "";
  const bytes = new Uint8Array(arrayBuffer);
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

async function fileToGeminiBase64(file, mimeType) {
  if (mimeType !== "image/jpeg") {
    return fileToBase64(file);
  }

  // Resize/compress JPGs to reduce Gemini request failures on large camera images.
  const compressed = await compressJpeg(file);
  return fileToBase64(compressed);
}

async function compressJpeg(file) {
  const imageUrl = URL.createObjectURL(file);
  try {
    const image = await loadImage(imageUrl);
    const maxDimension = 1600;
    const scale = Math.min(1, maxDimension / Math.max(image.width, image.height));
    const targetWidth = Math.max(1, Math.round(image.width * scale));
    const targetHeight = Math.max(1, Math.round(image.height * scale));

    const canvas = document.createElement("canvas");
    canvas.width = targetWidth;
    canvas.height = targetHeight;

    const context = canvas.getContext("2d");
    context.drawImage(image, 0, 0, targetWidth, targetHeight);

    const blob = await new Promise((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.78)
    );
    return blob || file;
  } finally {
    URL.revokeObjectURL(imageUrl);
  }
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Could not read selected image."));
    image.src = src;
  });
}

function showScreen(screen) {
  document.body.dataset.ambient = screen;
  screenIntro.classList.toggle("active", screen === "intro");
  screenHistory.classList.toggle("active", screen === "history");
  screenInput.classList.toggle("active", screen === "input");
  screenResults.classList.toggle("active", screen === "results");
  if (screenPlan) screenPlan.classList.toggle("active", screen === "plan");

  dotIntro.classList.toggle("active", screen === "intro");
  dotHistory.classList.toggle("active", screen === "history");
  dotInput.classList.toggle("active", screen === "input");
  dotResults.classList.toggle("active", screen === "results");
  if (navPlanBtn) navPlanBtn.classList.toggle("active", screen === "plan");
}

function planCellId(yearId, quarterId) {
  return `${yearId}-${quarterId}`;
}

/** Calendar quarter key (YYYY-Fall|Winter|Spring|Summer) for a planner cell, given graduation year G (spring of senior year). */
function quarterKeyForPlanCell(gradYear, yearId, quarterId) {
  const G = gradYear;
  const r = PLAN_YEARS.findIndex((y) => y.id === yearId);
  if (r < 0) return null;
  const cap = quarterId.charAt(0).toUpperCase() + quarterId.slice(1);
  if (quarterId === "fall") {
    return `${G - 4 + r}-Fall`;
  }
  return `${G - 3 + r}-${cap}`;
}

function findCellIdForSavedQuarter(gradYear, savedQuarterKey) {
  if (!savedQuarterKey || typeof gradYear !== "number" || Number.isNaN(gradYear)) {
    return null;
  }
  for (const year of PLAN_YEARS) {
    for (const q of PLAN_QUARTERS) {
      const key = quarterKeyForPlanCell(gradYear, year.id, q.id);
      if (key === savedQuarterKey) return planCellId(year.id, q.id);
    }
  }
  return null;
}

const PLAN_CELL_KEY_RE =
  /^(freshman|sophomore|junior|senior)-(fall|winter|spring|summer)$/;

function graduationYearRange() {
  const y = new Date().getFullYear();
  return { min: y, max: y + 5 };
}

function defaultGraduationYear() {
  const { min, max } = graduationYearRange();
  const preferred = min + 4;
  return Math.min(preferred, max);
}

function clampGraduationYearToRange(gy) {
  const { min, max } = graduationYearRange();
  if (typeof gy !== "number" || Number.isNaN(gy)) return null;
  return Math.min(max, Math.max(min, gy));
}

function fillGraduationYearSelect() {
  if (!planGraduationYearSelect) return;
  const { min, max } = graduationYearRange();
  planGraduationYearSelect.innerHTML = "";
  for (let y = min; y <= max; y++) {
    const opt = document.createElement("option");
    opt.value = String(y);
    opt.textContent = String(y);
    planGraduationYearSelect.appendChild(opt);
  }
}

function parseFourYearStoredPayload(raw) {
  if (!raw) return { graduationYear: null, cells: {}, includeSummer: true };
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    return { graduationYear: null, cells: {}, includeSummer: true };
  }
  if (!data || typeof data !== "object") {
    return { graduationYear: null, cells: {}, includeSummer: true };
  }
  const includeSummer = data.includeSummer !== false;
  if (data.cells && typeof data.cells === "object") {
    let gy = data.graduationYear;
    if (typeof gy === "string") gy = parseInt(gy, 10);
    if (typeof gy !== "number" || Number.isNaN(gy)) gy = null;
    gy = clampGraduationYearToRange(gy);
    return { graduationYear: gy, cells: data.cells, includeSummer };
  }
  const cells = {};
  for (const [k, v] of Object.entries(data)) {
    if (PLAN_CELL_KEY_RE.test(k) && typeof v === "string") cells[k] = v;
  }
  return { graduationYear: null, cells, includeSummer: true };
}

function initFourYearPlanGrid() {
  if (!fourYearTableBody || fourYearTableBody.dataset.inited === "1") return;
  fourYearTableBody.dataset.inited = "1";
  for (const year of PLAN_YEARS) {
    const tr = document.createElement("tr");
    const th = document.createElement("th");
    th.className = "four-year-year-label";
    th.scope = "row";
    th.textContent = year.label;
    tr.appendChild(th);
    for (const q of PLAN_QUARTERS) {
      const td = document.createElement("td");
      td.className = `plan-cell four-year-col four-year-col--${q.id}`;
      const ta = document.createElement("textarea");
      ta.className = "plan-cell-input";
      ta.rows = 5;
      ta.spellcheck = false;
      const cid = planCellId(year.id, q.id);
      ta.dataset.cellId = cid;
      ta.setAttribute("aria-label", `${year.label} ${q.label} — courses`);
      ta.placeholder = "Courses, units, notes…";
      td.appendChild(ta);
      tr.appendChild(td);
    }
    fourYearTableBody.appendChild(tr);
  }
}

function loadFourYearFromStorage() {
  if (!fourYearTableBody) return;
  fillGraduationYearSelect();
  const raw = localStorage.getItem(FOUR_YEAR_STORAGE_KEY);
  const { graduationYear, cells, includeSummer } = parseFourYearStoredPayload(raw);
  if (planGraduationYearSelect) {
    const y =
      graduationYear != null ? graduationYear : defaultGraduationYear();
    planGraduationYearSelect.value = String(y);
  }
  if (planIncludeSummerToggle) {
    planIncludeSummerToggle.checked = includeSummer !== false;
  }
  fourYearTableBody.querySelectorAll("[data-cell-id]").forEach((ta) => {
    const v = cells[ta.dataset.cellId];
    ta.value = typeof v === "string" ? v : "";
  });
  applyPlanSummerVisibility();
}

function readGraduationYearFromSelect() {
  if (!planGraduationYearSelect) return null;
  const n = parseInt(planGraduationYearSelect.value, 10);
  const clamped = clampGraduationYearToRange(n);
  return clamped;
}

function collectFourYearPlanForChat() {
  const cells = {};
  if (fourYearTableBody) {
    fourYearTableBody.querySelectorAll("[data-cell-id]").forEach((ta) => {
      cells[ta.dataset.cellId] = ta.value;
    });
  }
  return {
    graduationYear: readGraduationYearFromSelect(),
    cells,
    includeSummer: planIncludeSummerToggle ? planIncludeSummerToggle.checked : true
  };
}

function renderPlanChatMarkdown(el, markdown) {
  if (!el) return;
  const raw = markdown || "";
  const md = typeof window !== "undefined" ? window.marked : undefined;
  const purify = typeof window !== "undefined" ? window.DOMPurify : undefined;
  if (md && typeof md.parse === "function" && purify && typeof purify.sanitize === "function") {
    try {
      const html = md.parse(raw, { headerIds: false, mangle: false });
      el.classList.add("plan-chat-reply--md");
      el.innerHTML = purify.sanitize(html, { USE_PROFILES: { html: true } });
      return;
    } catch {
      /* fall through */
    }
  }
  el.classList.remove("plan-chat-reply--md");
  el.textContent = raw || "(Empty reply)";
}

function saveFourYearToStorage() {
  if (!fourYearTableBody) return;
  const cells = {};
  fourYearTableBody.querySelectorAll("[data-cell-id]").forEach((ta) => {
    cells[ta.dataset.cellId] = ta.value;
  });
  const graduationYear = readGraduationYearFromSelect();
  const includeSummer = planIncludeSummerToggle ? planIncludeSummerToggle.checked : true;
  const payload = { graduationYear, cells, includeSummer };
  try {
    localStorage.setItem(FOUR_YEAR_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    /* ignore quota */
  }
}

function wireFourYearSaveListeners() {
  if (fourYearListenersBound || !fourYearTableBody) return;
  fourYearListenersBound = true;
  let debounceTimer;
  const scheduleSave = () => {
    clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => saveFourYearToStorage(), 450);
  };
  fourYearTableBody.addEventListener("input", (event) => {
    if (!event.target.classList?.contains("plan-cell-input")) return;
    scheduleSave();
  });
  if (planGraduationYearSelect && !planGraduationYearSelect.dataset.saveBound) {
    planGraduationYearSelect.dataset.saveBound = "1";
    planGraduationYearSelect.addEventListener("change", () => {
      scheduleSave();
      if (planImportModal && !planImportModal.classList.contains("hidden")) {
        updatePlanImportPreview();
      }
    });
  }
  if (planIncludeSummerToggle && !planIncludeSummerToggle.dataset.bound) {
    planIncludeSummerToggle.dataset.bound = "1";
    planIncludeSummerToggle.addEventListener("change", () => {
      applyPlanSummerVisibility();
      saveFourYearToStorage();
    });
  }
}

function applyPlanSummerVisibility() {
  const table = document.getElementById("fourYearTable");
  const scroll = table?.closest(".four-year-scroll");
  if (!table || !planIncludeSummerToggle) return;
  const showSummer = planIncludeSummerToggle.checked;
  table.classList.toggle("four-year-grid--summer-off", !showSummer);
  if (scroll) scroll.classList.toggle("four-year-scroll--summer-off", !showSummer);
}

async function openPlanScreen() {
  initFourYearPlanGrid();
  wireFourYearSaveListeners();
  loadFourYearFromStorage();
  await loadSavedEntries();
  updateHistoryNavAvailability();
  showScreen("plan");
}

function buildPlanImportTargetOptions() {
  if (!planImportTargetSelect) return;
  planImportTargetSelect.innerHTML = "";
  for (const year of PLAN_YEARS) {
    for (const q of PLAN_QUARTERS) {
      const id = planCellId(year.id, q.id);
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = `${year.label} — ${q.label}`;
      planImportTargetSelect.appendChild(opt);
    }
  }
}

function populatePlanImportEntrySelect() {
  if (!planImportSelect) return;
  planImportSelect.innerHTML = "";
  if (!savedEntries.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No saved plans yet";
    planImportSelect.appendChild(opt);
    planImportSelect.disabled = true;
    return;
  }
  planImportSelect.disabled = false;
  for (const entry of savedEntries) {
    const opt = document.createElement("option");
    opt.value = String(entry.id);
    const qk = normalizeEntryQuarter(entry);
    const headline =
      entry.recommendations?.map((r) => r.course).slice(0, 3).join(" · ") ||
      "Saved plan";
    opt.textContent = qk ? `${labelQuarterKey(qk)} — ${headline}` : headline;
    planImportSelect.appendChild(opt);
  }
}

function getPlanImportSelectedEntry() {
  const id = planImportSelect?.value;
  if (!id) return null;
  return savedEntries.find((e) => String(e.id) === id) || null;
}

function formatImportedCourseBullets(entry) {
  const lines = (entry.recommendations || [])
    .slice(0, 3)
    .map((r) => {
      const c = typeof r.course === "string" ? r.course.trim() : "";
      return c ? `• ${c}` : "";
    })
    .filter(Boolean);
  return lines.join("\n").trim();
}

function updatePlanImportPreview(options = {}) {
  const applyAutoTarget = options.applyAutoTarget !== false;
  if (!planImportPreview) return;
  const entry = getPlanImportSelectedEntry();
  if (!entry) {
    planImportPreview.textContent = "";
    return;
  }
  let body = formatImportedCourseBullets(entry) || "(No courses in this save)";
  const G = readGraduationYearFromSelect();
  const qk = normalizeEntryQuarter(entry);
  const mappedCellId =
    G != null && qk && planImportTargetSelect
      ? findCellIdForSavedQuarter(G, qk)
      : null;

  if (!qk) {
    body += "\n\nCould not read this save’s quarter — pick “Place into” manually.";
  } else if (G == null) {
    body += "\n\nSelect a graduation year on the plan page for quarter matching.";
  } else if (planImportTargetSelect) {
    if (applyAutoTarget) {
      if (
        mappedCellId &&
        [...planImportTargetSelect.options].some((o) => o.value === mappedCellId)
      ) {
        planImportTargetSelect.value = mappedCellId;
      } else {
        body +=
          "\n\nNo slot on this four-year map matches that calendar quarter for your graduation year — pick “Place into” manually.";
      }
    } else if (
      mappedCellId &&
      planImportTargetSelect.value &&
      planImportTargetSelect.value !== mappedCellId
    ) {
      body += "\n\n(Using your selected cell instead of the quarter-mapped slot.)";
    }
  }

  if (planImportTargetSelect) {
    const opt = planImportTargetSelect.selectedOptions[0];
    if (opt) body += `\n\n→ ${opt.textContent}`;
  }

  planImportPreview.textContent = body;
}


function openPlanImportModal() {
  if (!planImportModal) return;
  populatePlanImportEntrySelect();
  buildPlanImportTargetOptions();
  updatePlanImportPreview();
  if (planImportApplyBtn) planImportApplyBtn.disabled = !savedEntries.length;
  planImportModal.classList.remove("hidden");
  planImportSelect?.focus();
}

function closePlanImportModal() {
  planImportModal?.classList.add("hidden");
}

function applyPlanImport() {
  const entry = getPlanImportSelectedEntry();
  if (!entry) return;
  const targetId = planImportTargetSelect?.value;
  if (!targetId) return;
  const ta = fourYearTableBody?.querySelector(`textarea[data-cell-id="${targetId}"]`);
  if (!ta) return;
  const block = formatImportedCourseBullets(entry);
  if (!block) return;
  const mode = document.querySelector('input[name="planImportMode"]:checked')?.value || "append";
  if (mode === "replace") {
    ta.value = block;
  } else {
    const cur = ta.value.trim();
    ta.value = cur ? `${cur}\n\n${block}` : block;
  }
  saveFourYearToStorage();
  closePlanImportModal();
}

if (navPlanBtn) {
  navPlanBtn.addEventListener("click", () => {
    openPlanScreen();
  });
}

if (openFourYearBtn) {
  openFourYearBtn.addEventListener("click", () => {
    openPlanScreen();
  });
}

if (historyToPlanBtn) {
  historyToPlanBtn.addEventListener("click", () => {
    openPlanScreen();
  });
}

if (backFromPlanBtn) {
  backFromPlanBtn.addEventListener("click", () => showScreen("intro"));
}

if (planChatSendBtn) {
  planChatSendBtn.addEventListener("click", async () => {
    const q = planChatQuestion?.value.trim() || "";
    if (!q) {
      if (planChatStatus) planChatStatus.textContent = "Add a question first.";
      return;
    }
    planChatSendBtn.disabled = true;
    if (planChatStatus) planChatStatus.textContent = "Thinking…";
    if (planChatError) {
      planChatError.textContent = "";
      planChatError.classList.add("hidden");
    }
    if (planChatReplyWrap) planChatReplyWrap.classList.add("hidden");
    if (planChatReply) {
      planChatReply.innerHTML = "";
      planChatReply.classList.remove("plan-chat-reply--md");
    }
    try {
      const response = await fetch("/api/plan-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q,
          fourYearPlan: collectFourYearPlanForChat()
        })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (planChatError) {
          let msg = data.error || `Request failed (${response.status}).`;
          if (response.status === 404) {
            msg =
              "404: /api/plan-chat was not found. Restart the app from prototypes/joey (`npm run dev`) so the latest server.js is running, and open the site from that server (http://localhost…), not as a file:// page.";
          }
          planChatError.textContent = msg;
          planChatError.classList.remove("hidden");
        }
        if (planChatStatus) planChatStatus.textContent = "";
        return;
      }
      const reply = typeof data.reply === "string" ? data.reply.trim() : "";
      renderPlanChatMarkdown(planChatReply, reply || "(Empty reply)");
      if (planChatReplyWrap) planChatReplyWrap.classList.remove("hidden");
      if (planChatStatus) planChatStatus.textContent = "Done.";
    } catch (err) {
      if (planChatError) {
        planChatError.textContent = err.message || "Network error.";
        planChatError.classList.remove("hidden");
      }
      if (planChatStatus) planChatStatus.textContent = "";
    } finally {
      planChatSendBtn.disabled = false;
    }
  });
}

if (planImportOpenBtn) {
  planImportOpenBtn.addEventListener("click", async () => {
    await loadSavedEntries();
    openPlanImportModal();
  });
}

if (planImportCancelBtn) {
  planImportCancelBtn.addEventListener("click", () => closePlanImportModal());
}

if (planImportBackdrop) {
  planImportBackdrop.addEventListener("click", () => closePlanImportModal());
}

if (planImportApplyBtn) {
  planImportApplyBtn.addEventListener("click", () => applyPlanImport());
}

if (planImportSelect) {
  planImportSelect.addEventListener("change", () => updatePlanImportPreview());
}

if (planImportTargetSelect) {
  planImportTargetSelect.addEventListener("change", () => {
    if (planImportModal && !planImportModal.classList.contains("hidden")) {
      updatePlanImportPreview({ applyAutoTarget: false });
    }
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && planImportModal && !planImportModal.classList.contains("hidden")) {
    closePlanImportModal();
  }
});

fillPlanQuarterSelect();

// Initialize History tab disabled state on page load.
loadSavedEntries();
