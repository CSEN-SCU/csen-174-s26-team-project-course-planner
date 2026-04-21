import { Router } from "express";
import { z } from "zod";
import { getEligibleCourseResults } from "../services/courseService.js";

const router = Router();

router.post("/eligible", async (req, res, next) => {
  try {
    const schema = z.object({
      completedCourses: z.array(z.string()).optional(),
      mode: z.enum(["balanced", "quality", "easy"]).optional(),
      filters: z.object({
        types: z.array(z.string()).optional(),
        divisions: z.array(z.string()).optional(),
        requirements: z.array(z.string()).optional(),
        timeWindow: z.string().optional()
      }).optional()
    });
    const payload = schema.parse(req.body ?? {});
    const results = await getEligibleCourseResults(payload);
    return res.json(results);
  } catch (error) {
    return next(error);
  }
});

export default router;
