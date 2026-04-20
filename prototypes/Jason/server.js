const express = require("express");
const cors = require("cors");
const path = require("path");
const fs = require("fs");
const Datastore = require("nedb-promises");
const dotenv = require("dotenv");
const { GoogleGenerativeAI } = require("@google/generative-ai");

dotenv.config();

const app = express();
const PORT = Number(process.env.PORT || 3001);

const dataDir = path.join(__dirname, "data");
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

const plansDb = Datastore.create({
  filename: path.join(dataDir, "plans.db"),
  autoload: true,
});

app.use(cors());
app.use(express.json({ limit: "2mb" }));
app.use(express.static(path.join(__dirname, "public")));

function createPrompt(payload) {
  const { persona, transcript, goals, constraints, priorities } = payload;
  return `
You are an academic planning assistant for SCU undergraduates.
Create 3 schedule recommendations for next quarter.

STUDENT PROFILE:
- Persona: ${persona}
- Goals: ${goals}
- Constraints: ${constraints}
- Priorities: ${priorities}

TRANSCRIPT / CONTEXT:
${transcript}

RESPONSE RULES:
1) Return valid JSON only.
2) Output this shape:
{
  "plans": [
    {
      "name": "string",
      "whyThisWorks": "string",
      "estimatedWorkload": "Low | Moderate | High",
      "qualityVsDifficultyNote": "string",
      "courses": [
        { "code": "string", "title": "string", "reason": "string" }
      ]
    }
  ],
  "advisorTip": "string"
}
3) Keep each plan realistic and explain tradeoffs clearly.
4) Respect time constraints and in-season training load.
`.trim();
}

async function generateRecommendations(payload) {
  const key = process.env.GEMINI_API_KEY;
  if (!key) {
    return {
      plans: [
        {
          name: "Balanced In-Season Plan",
          whyThisWorks:
            "Prioritizes required progress while controlling weekly workload for a 20-hour athletics commitment.",
          estimatedWorkload: "Moderate",
          qualityVsDifficultyNote:
            "Favors stronger teaching quality for major classes while selecting manageable electives.",
          courses: [
            {
              code: "COEN 146",
              title: "Computer Networks",
              reason: "Keeps major progress on track with structured, predictable weekly deliverables.",
            },
            {
              code: "MATH 53",
              title: "Applied Statistics",
              reason: "Supports data literacy with moderate workload and practical relevance.",
            },
            {
              code: "THTR 20",
              title: "Public Speaking",
              reason: "Lower reading load and strong communication upside.",
            },
          ],
        },
        {
          name: "GPA-Stability Plan",
          whyThisWorks:
            "Emphasizes consistency and reduced workload spikes during travel weeks.",
          estimatedWorkload: "Low",
          qualityVsDifficultyNote:
            "Optimizes for manageable difficulty and stable performance through season.",
          courses: [
            {
              code: "COEN 170",
              title: "Operating Systems",
              reason: "Core requirement with clear milestones and team support opportunities.",
            },
            {
              code: "ENGL 106",
              title: "Business Writing",
              reason: "Useful for internships and typically steady, predictable assignments.",
            },
            {
              code: "PHIL 2",
              title: "Ethics",
              reason: "Balances the technical schedule with lighter problem-set pressure.",
            },
          ],
        },
        {
          name: "Career-Edge Plan",
          whyThisWorks:
            "Adds one challenging career-oriented class while keeping the rest of the schedule manageable.",
          estimatedWorkload: "High",
          qualityVsDifficultyNote:
            "Trades higher difficulty in one course for stronger career skill growth.",
          courses: [
            {
              code: "COEN 174",
              title: "Machine Learning",
              reason: "Career-relevant depth course with project portfolio value.",
            },
            {
              code: "COEN 171",
              title: "Web Programming",
              reason: "Practical full-stack skill building with direct internship relevance.",
            },
            {
              code: "COMM 12",
              title: "Media and Society",
              reason: "Offsets technical intensity with a discussion-based class.",
            },
          ],
        },
      ],
      advisorTip:
        "Add your GEMINI_API_KEY in .env to replace these seeded plans with AI-generated recommendations.",
    };
  }

  const genAI = new GoogleGenerativeAI(key);
  const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });
  const prompt = createPrompt(payload);
  const response = await model.generateContent(prompt);
  const text = response.response.text().trim();
  const parsed = JSON.parse(text.replace(/^```json|```$/g, "").trim());
  return parsed;
}

app.post("/api/recommend", async (req, res) => {
  try {
    const { persona, transcript, goals, constraints, priorities } = req.body;
    if (!persona || !transcript || !goals || !constraints || !priorities) {
      return res.status(400).json({ error: "Missing required wizard fields." });
    }

    const recommendations = await generateRecommendations(req.body);
    const saved = await plansDb.insert({
      createdAt: new Date().toISOString(),
      input: { persona, goals, constraints, priorities },
      output: recommendations,
    });

    return res.json({
      id: saved._id,
      ...recommendations,
    });
  } catch (error) {
    return res.status(500).json({
      error: "Failed to generate recommendations.",
      details: error.message,
    });
  }
});

app.get("/api/plans", async (_req, res) => {
  const plans = await plansDb.find({}).sort({ createdAt: -1 }).limit(10);
  res.json(plans);
});

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, service: "Jason prototype API" });
});

app.use((_req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

app.listen(PORT, () => {
  console.log(`Prototype running at http://localhost:${PORT}`);
});
