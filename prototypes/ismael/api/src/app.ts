import cors from "cors";
import express from "express";
import transcriptRoutes from "./routes/transcript.js";
import courseRoutes from "./routes/courses.js";
import scheduleRoutes from "./routes/schedule.js";

export function createApp() {
  const app = express();
  app.use(cors({ origin: process.env.CLIENT_ORIGIN ?? "http://localhost:5173" }));
  app.use(express.json({ limit: "1mb" }));
  const aiProvider = "OpenAI";
  const aiModel = process.env.OPENAI_MODEL ?? "gpt-4o-mini";
  const aiEnabled = (process.env.OPENAI_ENABLED ?? "false").toLowerCase() === "true";

  app.get("/health", (_req, res) => {
    res.json({ ok: true, service: "bronco-plan-api", aiProvider, aiModel, aiEnabled });
  });

  app.use("/transcript", transcriptRoutes);
  app.use("/courses", courseRoutes);
  app.use("/schedule", scheduleRoutes);

  app.use((error: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    const message = error instanceof Error ? error.message : "Unknown server error";
    res.status(400).json({ error: message });
  });

  return app;
}
