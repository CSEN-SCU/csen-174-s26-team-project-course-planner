import cors from "cors";
import express from "express";
import transcriptRoutes from "./routes/transcript.js";
import courseRoutes from "./routes/courses.js";
import scheduleRoutes from "./routes/schedule.js";
import { getAiHealth } from "./ai/scheduleAi.js";

export function createApp() {
  const app = express();
  app.use(cors({ origin: process.env.CLIENT_ORIGIN ?? "http://localhost:5173" }));
  app.use(express.json({ limit: "1mb" }));
  const { aiProvider, aiModel, aiEnabled } = getAiHealth(process.env);

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
