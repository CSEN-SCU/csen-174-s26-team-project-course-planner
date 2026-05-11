import cors from "cors";
import express from "express";

export function createApp() {
  const app = express();
  app.use(cors());
  app.use(express.json());

  // Minimal contract endpoint for tests.
  app.get("/courses/requirements/:major", (req, res) => {
    const major = String(req.params.major ?? "");
    res.status(200).json({
      major,
      requiredCourses: [
        { code: "ENGR 1", name: "Introduction to Engineering" },
        { code: "CSEN 174", name: "Software Engineering" }
      ]
    });
  });

  return app;
}

