# Ismael Prototype API

Express + Prisma + SQLite backend for the Bronco Plan prototype.

## Stack

- Node.js + TypeScript + Express
- Prisma + SQLite
- Gemini API (with fallback stub when no key is configured)
- Zod validation

## Setup

```bash
cd prototypes/ismael/api
cp .env.example .env
npm install
npm run prisma:migrate
npm run prisma:seed
npm run dev
```

Server defaults to `http://localhost:8080`.

## Environment

- `PORT` - API port
- `CLIENT_ORIGIN` - frontend origin for CORS
- `DATABASE_URL` - SQLite file path for Prisma
- `GEMINI_ENABLED` - set `true` to allow live Gemini calls; default demo-safe mode is `false`
- `GEMINI_API_KEY` - optional; if omitted, schedule endpoints return fallback plans
- `GEMINI_MODEL` - defaults to `gemini-2.5-flash-lite`

## Sample curl requests

```bash
curl -X POST http://localhost:8080/transcript/parse   -H "Content-Type: application/json"   -d '{"fileName":"ismael-transfer-transcript.pdf"}'
```

```bash
curl -X POST http://localhost:8080/courses/eligible   -H "Content-Type: application/json"   -d '{"completedCourses":["CSE 30","CSE 101","MATH 11"],"mode":"balanced","filters":{"types":["major"],"timeWindow":"Morning"}}'
```

```bash
curl -X POST http://localhost:8080/schedule/recommend   -H "Content-Type: application/json"   -d '{"selectedDesiredCourses":["CSE 146","ELSJ 152"],"priorities":"quality","remainingRequirements":["ELSJ"]}'
```

```bash
curl -X POST http://localhost:8080/schedule/export-ics   -H "Content-Type: application/json"   -d '{"items":[{"courseCode":"CSE 146","courseName":"Database Systems","days":"MW","startTime":"12:00","endTime":"13:40","instructor":"Dr. Li"}]}'
```

## Known limitations

- Transcript parsing is mock/heuristic, not OCR or PDF extraction.
- Prerequisite checking supports simple `all-of` prerequisite code arrays only.
- AI plans are only fully dynamic when `GEMINI_ENABLED=true` and `GEMINI_API_KEY` is set.
- `.ics` export returns calendar content JSON for easy frontend download handling.
