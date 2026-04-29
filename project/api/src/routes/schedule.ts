import { Router } from "express";
import { z } from "zod";
import { generateScheduleChatReply, generateSchedulePlans } from "../ai/scheduleAi.js";
import { buildIcs } from "../utils/ics.js";
import { findConflicts } from "../utils/conflicts.js";

const router = Router();

const scheduleSchema = z.object({
  selectedDesiredCourses: z.array(z.string()).optional(),
  completedCourses: z.array(z.string()).optional(),
  priorities: z.enum(["balanced", "quality", "easy"]).optional(),
  remainingRequirements: z.array(z.string()).optional(),
  constraints: z.object({
    maxCourses: z.number().int().optional(),
    timeWindow: z.string().optional()
  }).optional(),
  existingSchedule: z.array(z.object({
    courseCode: z.string(),
    days: z.string().optional(),
    time: z.string().optional()
  })).optional()
});

const chatSchema = scheduleSchema.extend({
  message: z.string().min(1)
});

router.post("/chat", async (req, res, next) => {
  try {
    const payload = chatSchema.parse(req.body ?? {});
    const reply = await generateScheduleChatReply(payload, payload.message);
    return res.json(reply);
  } catch (error) {
    return next(error);
  }
});

router.post("/complete", async (req, res, next) => {
  try {
    const payload = scheduleSchema.parse(req.body ?? {});
    const plans = await generateSchedulePlans("complete", payload);
    return res.json(plans);
  } catch (error) {
    return next(error);
  }
});

router.post("/export-ics", (req, res, next) => {
  try {
    const schema = z.object({
      items: z.array(z.object({
        courseCode: z.string(),
        courseName: z.string(),
        days: z.string().optional(),
        startTime: z.string().optional(),
        endTime: z.string().optional(),
        instructor: z.string().optional()
      }))
    });
    const payload = schema.parse(req.body ?? {});
    const conflicts = findConflicts(payload.items.map((item) => ({
      courseCode: item.courseCode,
      days: item.days ?? "M",
      startTime: item.startTime ?? "09:00",
      endTime: item.endTime ?? "10:00"
    })));
    res.setHeader("Content-Type", "text/calendar; charset=utf-8");
    return res.json({
      filename: "bronco-plan.ics",
      content: buildIcs(payload.items),
      conflicts
    });
  } catch (error) {
    return next(error);
  }
});

export default router;
