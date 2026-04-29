import { Router } from "express";
import { z } from "zod";
import { buildTranscriptSummary } from "../services/transcriptService.js";

const router = Router();

router.post("/parse", (req, res) => {
  const schema = z.object({
    fileName: z.string().optional(),
    transcriptText: z.string().optional()
  });
  const payload = schema.parse(req.body ?? {});
  return res.json(buildTranscriptSummary(payload.fileName, payload.transcriptText));
});

export default router;
