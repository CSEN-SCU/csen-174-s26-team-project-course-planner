# Jason Prototype: Guided Wizard Planner

This prototype explores an advisor-style guided wizard for SCU course planning. It is designed for students with strict time limits (for example, D1 athletes with 20-hour training weeks) and generates explainable schedule options with quality-vs-difficulty tradeoffs.

## Tech stack
- Frontend: HTML/CSS/JavaScript (single-page wizard UI)
- Backend: Node.js + Express
- Database: NeDB (embedded file database persisted in `data/plans.db`)
- AI integration: Google Gemini API (`@google/generative-ai`)

## Run locally
1. Create a `.env` file in **this same folder as `server.js`** (`prototypes/Jason/.env`):
   - `GEMINI_API_KEY=your_key_here`
   - `PORT=3001` (optional)
2. Install dependencies:
   - `npm install`
3. Start the prototype:
   - `npm start` (recommended)
   - or `npm run dev` (auto-restarts when you edit server code)
4. Open:
   - `http://localhost:3001`

## Demo notes
- If `GEMINI_API_KEY` is missing, the app still runs using seeded fallback plans.
- After editing `.env`, restart the server so the key reloads.
- `GET /api/health` includes `geminiConfigured: true/false` for a quick check.
- Every generated result is saved and can be retrieved from `GET /api/plans`.
