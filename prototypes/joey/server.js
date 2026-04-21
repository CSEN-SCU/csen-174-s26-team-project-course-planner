const path = require("path");
const fs = require("fs/promises");
const express = require("express");
const dotenv = require("dotenv");

dotenv.config({ path: path.join(__dirname, ".env") });

const app = express();
const PORT = process.env.PORT || 3000;
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const GEMINI_MODEL = process.env.GEMINI_MODEL || "gemini-2.5-flash";
const SCU_BULLETIN_URL =
  "https://www.scu.edu/bulletin/undergraduate/chapter-5-school-of-engineering/computer-science-and-engineering.html#59ffa8ec905c";
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ALLOWED_MIME_TYPES = new Set(["application/pdf", "image/jpeg", "text/plain"]);
const MAJORS_DB_PATH = path.join(__dirname, "data", "majors.compact.json");
const SAVED_OUTPUTS_PATH = path.join(__dirname, "data", "saved-outputs.json");
const QUARTER_KEY_RE = /^(\d{4})-(Fall|Winter|Spring)$/;

app.use(express.json({ limit: "15mb" }));

let cachedBulletinSnippet = "";
let bulletinFetchedAt = 0;
let cachedMajorsDb = null;

function stripMarkdownCodeFence(input = "") {
  return input
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();
}

function parseTopThreeResponse(modelText = "") {
  const cleaned = stripMarkdownCodeFence(modelText);
  const parsed = JSON.parse(cleaned);
  const recommendations = Array.isArray(parsed?.recommendations)
    ? parsed.recommendations
        .map((item) => ({
          course: typeof item?.course === "string" ? item.course.trim() : "",
          reason: typeof item?.reason === "string" ? item.reason.trim() : ""
        }))
        .filter((item) => item.course && item.reason)
        .slice(0, 3)
    : [];
  const summary = typeof parsed?.summary === "string" ? parsed.summary.trim() : "";
  return { recommendations, summary };
}

function inferMimeTypeFromName(fileName = "") {
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".pdf")) return "application/pdf";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  if (lower.endsWith(".txt")) return "text/plain";
  return "";
}

function compactWhitespace(input = "") {
  return input.replace(/\s+/g, " ").trim();
}

async function callGemini(parts) {
  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_API_KEY}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [
          {
            parts
          }
        ]
      })
    }
  );

  if (!response.ok) {
    const details = await response.text();
    return {
      ok: false,
      status: response.status,
      details
    };
  }

  const data = await response.json();
  const text =
    data?.candidates?.[0]?.content?.parts
      ?.map((part) => part.text || "")
      .join("\n")
      .trim() || "";

  return { ok: true, text };
}

async function getBulletinSnippet() {
  const now = Date.now();
  const tenMinutes = 10 * 60 * 1000;
  if (cachedBulletinSnippet && now - bulletinFetchedAt < tenMinutes) {
    return cachedBulletinSnippet;
  }

  try {
    const response = await fetch(SCU_BULLETIN_URL);
    if (!response.ok) {
      throw new Error(`Failed to fetch bulletin: ${response.status}`);
    }
    const html = await response.text();
    const text = compactWhitespace(
      html
        .replace(/<script[\s\S]*?<\/script>/gi, " ")
        .replace(/<style[\s\S]*?<\/style>/gi, " ")
        .replace(/<[^>]+>/g, " ")
    );

    // Keep prompt length controlled while still passing real bulletin context.
    cachedBulletinSnippet = text.slice(0, 12000);
    bulletinFetchedAt = now;
    return cachedBulletinSnippet;
  } catch {
    return "";
  }
}

async function loadMajorsDb() {
  if (cachedMajorsDb) return cachedMajorsDb;
  try {
    const raw = await fs.readFile(MAJORS_DB_PATH, "utf8");
    cachedMajorsDb = JSON.parse(raw);
    return cachedMajorsDb;
  } catch {
    return null;
  }
}

function buildCompactMajorsContext(db) {
  if (!db || !Array.isArray(db.records) || !Array.isArray(db.dictionary)) {
    return "";
  }

  const lines = db.records.map((record) => {
    const courses = (record.c || [])
      .map((index) => db.dictionary[index])
      .filter(Boolean)
      .slice(0, 40);
    return `${record.m}: ${courses.join(", ")}`;
  });

  // Keep model context compact and deterministic.
  return lines.join("\n").slice(0, 9000);
}

function dateToCurrentQuarter(d) {
  const m = d.getMonth();
  const y = d.getFullYear();
  if (m >= 8) return { season: "Fall", year: y };
  if (m <= 2) return { season: "Winter", year: y };
  if (m <= 5) return { season: "Spring", year: y };
  return { season: "Fall", year: y };
}

function formatQuarterKey(q) {
  return `${q.year}-${q.season}`;
}

function isValidQuarterKey(key) {
  return typeof key === "string" && QUARTER_KEY_RE.test(key);
}

function inferQuarterKeyFromSavedAt(iso) {
  const d = new Date(iso || Date.now());
  return formatQuarterKey(dateToCurrentQuarter(d));
}

function migrateSavedEntry(entry) {
  if (!entry || typeof entry !== "object") return entry;
  if (isValidQuarterKey(entry.quarter)) return entry;
  return { ...entry, quarter: inferQuarterKeyFromSavedAt(entry.savedAt) };
}

function getEntryQuarterKey(entry) {
  return isValidQuarterKey(entry?.quarter) ? entry.quarter : inferQuarterKeyFromSavedAt(entry?.savedAt);
}

function applyQuarterReorder(entries, quarterKey, newOrderIds) {
  const normalized = entries.map((e) => ({ ...e, quarter: getEntryQuarterKey(e) }));
  const inQuarter = normalized.filter((e) => e.quarter === quarterKey);
  const idSet = new Set(inQuarter.map((e) => String(e.id)));
  const normOrder = newOrderIds.map((id) => String(id));
  if (normOrder.length !== idSet.size) {
    throw new Error("BAD_REORDER");
  }
  for (const id of normOrder) {
    if (!idSet.has(id)) throw new Error("BAD_REORDER");
  }
  const byId = new Map(normalized.map((e) => [String(e.id), e]));
  const reorderedBlock = normOrder.map((id) => byId.get(id));
  let qi = 0;
  return normalized.map((e) => {
    if (e.quarter === quarterKey) return reorderedBlock[qi++];
    return e;
  });
}

async function loadSavedOutputs() {
  try {
    const raw = await fs.readFile(SAVED_OUTPUTS_PATH, "utf8");
    const parsed = JSON.parse(raw);
    const arr = Array.isArray(parsed) ? parsed : [];
    return arr.map(migrateSavedEntry);
  } catch {
    return [];
  }
}

async function writeSavedOutputs(entries) {
  await fs.mkdir(path.dirname(SAVED_OUTPUTS_PATH), { recursive: true });
  const payload = JSON.stringify(entries);
  const tmpPath = `${SAVED_OUTPUTS_PATH}.tmp`;
  await fs.writeFile(tmpPath, payload, "utf8");
  try {
    await fs.rename(tmpPath, SAVED_OUTPUTS_PATH);
  } catch {
    await fs.writeFile(SAVED_OUTPUTS_PATH, payload, "utf8");
    await fs.rm(tmpPath, { force: true });
  }
}

app.get("/api/saved-outputs", async (req, res) => {
  const entries = await loadSavedOutputs();
  return res.json({
    count: entries.length,
    entries
  });
});

app.delete("/api/saved-outputs", async (req, res) => {
  await writeSavedOutputs([]);
  return res.json({ cleared: true });
});

app.put("/api/saved-outputs/reorder", async (req, res) => {
  const quarterKey = typeof req.body?.quarter === "string" ? req.body.quarter.trim() : "";
  const order = req.body?.order;
  if (!isValidQuarterKey(quarterKey)) {
    return res.status(400).json({
      error: "Body must include quarter in the form YYYY-Fall, YYYY-Winter, or YYYY-Spring."
    });
  }
  if (!Array.isArray(order) || !order.every((id) => typeof id === "string")) {
    return res.status(400).json({
      error: "Body must include order: string[] of entry ids for that quarter only."
    });
  }
  const entries = await loadSavedOutputs();
  try {
    const reordered = applyQuarterReorder(entries, quarterKey, order);
    await writeSavedOutputs(reordered);
    return res.json({ reordered: true, count: reordered.length, quarter: quarterKey });
  } catch {
    return res.status(400).json({
      error: "Reorder must be a permutation of all saved ids for the selected quarter."
    });
  }
});

app.delete("/api/saved-outputs/:id", async (req, res) => {
  const id = String(req.params.id);
  const entries = await loadSavedOutputs();
  const next = entries.filter((entry) => String(entry.id) !== id);
  if (next.length === entries.length) {
    return res.status(404).json({ error: "Entry not found." });
  }
  await writeSavedOutputs(next);
  return res.json({ deleted: true, id });
});

app.post("/api/saved-outputs", async (req, res) => {
  const recommendations = Array.isArray(req.body?.recommendations)
    ? req.body.recommendations
        .map((item) => ({
          course: typeof item?.course === "string" ? item.course.trim() : "",
          reason: typeof item?.reason === "string" ? item.reason.trim() : ""
        }))
        .filter((item) => item.course && item.reason)
        .slice(0, 3)
    : [];
  const summary = typeof req.body?.summary === "string" ? req.body.summary.trim() : "";
  const quarterRaw = typeof req.body?.quarter === "string" ? req.body.quarter.trim() : "";

  if (recommendations.length !== 3 || !summary) {
    return res.status(400).json({
      error: "Save failed: provide exactly 3 recommendations and a summary."
    });
  }

  if (!isValidQuarterKey(quarterRaw)) {
    return res.status(400).json({
      error: "Save failed: quarter must be YYYY-Fall, YYYY-Winter, or YYYY-Spring."
    });
  }

  const entries = await loadSavedOutputs();
  const savedAt = new Date().toISOString();
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const record = {
    id,
    savedAt,
    quarter: quarterRaw,
    recommendations,
    summary
  };
  entries.unshift(record);
  await writeSavedOutputs(entries.slice(0, 100));

  return res.status(201).json({ saved: true, id, savedAt });
});

app.get("/api/majors-db", async (req, res) => {
  const db = await loadMajorsDb();
  if (!db) {
    return res.status(404).json({
      error:
        "Majors DB not found. Run `npm run build:majors-db` from prototypes/joey to generate it."
    });
  }

  const sampleRecords = db.records.slice(0, 5);
  const cseRecord = db.records.find((record) =>
    typeof record.m === "string" &&
    record.m.toLowerCase().includes("computer science and engineering")
  );
  if (
    cseRecord &&
    !sampleRecords.some((record) => record.m === cseRecord.m)
  ) {
    sampleRecords[sampleRecords.length - 1] = cseRecord;
  }

  return res.json({
    generatedAt: db.generatedAt,
    source: db.source,
    majorsCount: db.records.length,
    uniqueCoursesCount: db.dictionary.length,
    sample: sampleRecords.map((record) => ({
      major: record.m,
      requiredCourses: (record.c || []).map((i) => db.dictionary[i]).filter(Boolean)
    }))
  });
});

app.post("/api/suggest-courses", async (req, res) => {
  if (!GEMINI_API_KEY) {
    return res.status(500).json({
      error:
        "GEMINI_API_KEY is not set. Add it to prototypes/joey/.env and restart the server."
    });
  }

  const transcriptText =
    typeof req.body?.transcriptText === "string" ? req.body.transcriptText.trim() : "";
  const filePayload = req.body?.file;
  const hasFilePayload =
    filePayload &&
    typeof filePayload === "object" &&
    typeof filePayload.dataBase64 === "string" &&
    filePayload.dataBase64.length > 0;

  if (!transcriptText && !hasFilePayload) {
    return res.status(400).json({
      error:
        "Provide transcript text or upload a JPG, PDF, or TXT file before requesting suggestions."
    });
  }

  if (hasFilePayload) {
    const mimeTypeFromInput =
      typeof filePayload.mimeType === "string" ? filePayload.mimeType.trim().toLowerCase() : "";
    const mimeTypeFromName = inferMimeTypeFromName(filePayload.fileName || "");
    const mimeType = mimeTypeFromInput || mimeTypeFromName;

    if (!ALLOWED_MIME_TYPES.has(mimeType)) {
      return res.status(400).json({
        error: "Unsupported file type. Upload a .jpg, .jpeg, .pdf, or .txt file."
      });
    }

    const estimatedBytes = Buffer.byteLength(filePayload.dataBase64, "base64");
    if (estimatedBytes > MAX_UPLOAD_BYTES) {
      return res.status(400).json({
        error: "File is too large. Keep uploads under 10MB for now."
      });
    }
  }

  const bulletinSnippet = await getBulletinSnippet();
  const majorsDb = await loadMajorsDb();
  const majorsContext = buildCompactMajorsContext(majorsDb);

  const instructionBlock = [
    "You are helping an SCU student plan next quarter courses.",
    `Use the SCU CSE bulletin page at ${SCU_BULLETIN_URL} and the provided bulletin excerpt for program context.`,
    "Interpret the transcript information from all provided modalities (text, PDF, or image).",
    "Return ONLY valid JSON with exactly three course recommendations and one short summary.",
    'Use this exact schema: {"recommendations":[{"course":"...","reason":"..."},{"course":"...","reason":"..."},{"course":"...","reason":"..."}],"summary":"..."}',
    "Each reason should be one sentence and concise.",
    "The summary should be 1-2 sentences that connect the three choices as a balanced next-step plan.",
    "Avoid recommending courses that appear already completed.",
    "If uncertainty exists, mention assumptions briefly in the summary.",
    "Do not output markdown, code fences, or any text outside JSON."
  ].join("\n");

  try {
    const parts = [{ text: instructionBlock }];
    if (transcriptText) {
      parts.push({
        text: `Transcript text provided by user:\n${transcriptText}`
      });
    }

    if (bulletinSnippet && !majorsContext) {
      parts.push({
        text: `SCU bulletin excerpt:\n${bulletinSnippet}`
      });
    }
    if (majorsContext) {
      parts.push({
        text: `SCU compact majors requirements database (major: required course list):\n${majorsContext}`
      });
    }

    if (hasFilePayload) {
      const mimeTypeFromInput =
        typeof filePayload.mimeType === "string" ? filePayload.mimeType.trim().toLowerCase() : "";
      const mimeTypeFromName = inferMimeTypeFromName(filePayload.fileName || "");
      const mimeType = mimeTypeFromInput || mimeTypeFromName;
      parts.push({
        inlineData: {
          mimeType,
          data: filePayload.dataBase64
        }
      });
      parts.push({
        text: `Uploaded filename: ${filePayload.fileName || "unknown"}`
      });
    }

    let geminiResult = await callGemini(parts);
    if (!geminiResult.ok && bulletinSnippet) {
      // Retry once with less context. This improves reliability for large image/PDF inputs.
      const fallbackParts = parts.filter(
        (part) => !part.text || !part.text.startsWith("SCU bulletin excerpt:")
      );
      geminiResult = await callGemini(fallbackParts);
    }

    if (!geminiResult.ok) {
      return res.status(500).json({
        error: "Gemini API request failed.",
        details: `Gemini status ${geminiResult.status}: ${geminiResult.details}`
      });
    }

    const modelText = geminiResult.text;

    if (!modelText) {
      return res.status(500).json({
        error: "Gemini returned no text response."
      });
    }

    let formatted;
    try {
      formatted = parseTopThreeResponse(modelText);
    } catch {
      return res.status(500).json({
        error: "Could not parse Gemini output in top-3 JSON format.",
        details: modelText
      });
    }

    if (formatted.recommendations.length < 3 || !formatted.summary) {
      return res.status(500).json({
        error: "Gemini returned incomplete top-3 recommendations.",
        details: modelText
      });
    }

    return res.json(formatted);
  } catch (error) {
    return res.status(500).json({
      error: "Unexpected server error while requesting Gemini.",
      details: error.message
    });
  }
});

function formatFourYearPlanForPrompt(plan) {
  const emptyMsg =
    "(The student did not send a structured grid, or all course cells are empty.)";
  if (!plan || typeof plan !== "object") return emptyMsg;
  const cells = plan.cells && typeof plan.cells === "object" ? plan.cells : {};
  const gy = plan.graduationYear;
  const years = [
    ["freshman", "Freshman"],
    ["sophomore", "Sophomore"],
    ["junior", "Junior"],
    ["senior", "Senior"]
  ];
  const includeSummer = plan.includeSummer !== false;
  const seasons = includeSummer
    ? ["fall", "winter", "spring", "summer"]
    : ["fall", "winter", "spring"];
  const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
  const lines = [];
  if (gy != null && typeof gy === "number" && !Number.isNaN(gy)) {
    lines.push(`Target graduation year (spring of senior year): ${gy}`);
  } else {
    lines.push("Graduation year: not specified");
  }
  if (!includeSummer) {
    lines.push("Student view: summer quarter column is hidden (three-term view).");
  }
  lines.push("");
  let any = false;
  for (const [yid, ylabel] of years) {
    const rowParts = [];
    for (const sid of seasons) {
      const key = `${yid}-${sid}`;
      const raw = cells[key];
      const txt = typeof raw === "string" ? raw.trim() : "";
      if (txt) {
        any = true;
        rowParts.push(`${cap(sid)}: ${txt.replace(/\s*\n+\s*/g, " / ")}`);
      }
    }
    if (rowParts.length) {
      lines.push(`${ylabel}:`);
      for (const p of rowParts) lines.push(`  ${p}`);
      lines.push("");
    }
  }
  if (!any) return emptyMsg;
  return lines.join("\n").slice(0, 14000);
}

app.get("/api/plan-chat", (req, res) => {
  res.status(200).json({
    ok: true,
    message: "Use POST with JSON body: { question: string, fourYearPlan?: { graduationYear, cells } }."
  });
});

app.post("/api/plan-chat", async (req, res) => {
  if (!GEMINI_API_KEY) {
    return res.status(500).json({
      error:
        "GEMINI_API_KEY is not set. Add it to prototypes/joey/.env and restart the server."
    });
  }

  const question =
    typeof req.body?.question === "string" ? req.body.question.trim() : "";
  if (!question) {
    return res.status(400).json({ error: "Provide a non-empty question." });
  }
  if (question.length > 4000) {
    return res.status(400).json({ error: "Question must be 4000 characters or less." });
  }

  const rawPlan = req.body?.fourYearPlan;
  const fourYearPlan =
    rawPlan && typeof rawPlan === "object"
      ? {
          graduationYear:
            typeof rawPlan.graduationYear === "number" && !Number.isNaN(rawPlan.graduationYear)
              ? rawPlan.graduationYear
              : null,
          cells:
            rawPlan.cells && typeof rawPlan.cells === "object" ? rawPlan.cells : {},
          includeSummer: rawPlan.includeSummer !== false
        }
      : null;

  const bulletinSnippet = await getBulletinSnippet();
  const majorsDb = await loadMajorsDb();
  const majorsContext = buildCompactMajorsContext(majorsDb);
  const planText = formatFourYearPlanForPrompt(fourYearPlan);

  const instructionBlock = [
    "You are an academic planning assistant for Santa Clara University (SCU) undergraduate students.",
    `Ground answers in the official SCU School of Engineering Computer Science and Engineering program context when relevant: ${SCU_BULLETIN_URL}`,
    "The student sketched a four-year course grid (by term) below. They may use shorthand or informal course names. Interpret generously and note assumptions.",
    "Answer their question in a natural, conversational tone. Tailor advice to their grid and graduation timing when possible.",
    "Use the bulletin excerpt and any majors requirements data to comment on prerequisites, sequencing, workload balance, and degree-structure fit—but do not claim official degree-audit or Workday truth.",
    "If context is incomplete, say so briefly and give best-effort guidance.",
    "Use markdown when it helps: ### headings, **bold**, bullet or numbered lists, short fenced code blocks for course codes.",
    "Do not recommend academic dishonesty or policy violations."
  ].join("\n");

  try {
    const parts = [{ text: instructionBlock }];
    parts.push({ text: `Student four-year sketch:\n${planText}` });
    if (bulletinSnippet && !majorsContext) {
      parts.push({
        text: `SCU CSE bulletin excerpt (undergraduate requirements context):\n${bulletinSnippet}`
      });
    }
    if (majorsContext) {
      parts.push({
        text: `SCU compact majors requirements database (major: required course list):\n${majorsContext}`
      });
    }
    parts.push({ text: `Student question:\n${question}` });

    let geminiResult = await callGemini(parts);
    if (!geminiResult.ok && bulletinSnippet) {
      const lean = parts.filter(
        (part) =>
          !part.text || !part.text.startsWith("SCU CSE bulletin excerpt (undergraduate")
      );
      geminiResult = await callGemini(lean);
    }

    if (!geminiResult.ok) {
      return res.status(500).json({
        error: "Gemini API request failed.",
        details: `Gemini status ${geminiResult.status}: ${geminiResult.details}`
      });
    }

    const reply = geminiResult.text || "";
    if (!reply.trim()) {
      return res.status(500).json({
        error: "Gemini returned an empty reply."
      });
    }

    return res.json({ reply: reply.trim() });
  } catch (error) {
    return res.status(500).json({
      error: "Unexpected server error while answering your plan question.",
      details: error.message
    });
  }
});

app.use(express.static(path.join(__dirname, "public")));

app.listen(PORT, () => {
  console.log(`SCU Course Planner running at http://localhost:${PORT}`);
  console.log("API routes include POST /api/plan-chat (GET /api/plan-chat = health check).");
});
