# How to run tests

All tests live under `project/course_planner/tests/`. They are wired into two
Vitest entry points so they can run from either side of the codebase:

- **Frontend / full suite** — `project/web/package.json` (jsdom env, runs every
  `*.test.ts` and `*.test.tsx`).
- **Backend / API only** — `project/api/package.json` (node env, runs the
  Express + auth tests that don't need a DOM).

Both runners load `project/vitest.config.ts` (web) or
`project/api/vitest.config.ts` (api), which point at this folder.

## Test layout

```
project/course_planner/tests/
├── api/                       backend-style tests (supertest, Prisma mocks)
│   ├── ai_generated/sprint1/  Jiasheng's AI-generated auth tests
│   ├── courses/               Joey's course-requirements API tests
│   └── database/              Joey's Prisma reset utility tests
├── ismael/                    Ismael's React component / a11y tests (jsdom)
└── jason/                     Jason's AI planning behavior + roadmap tests
```

Bridge modules in `project/course_planner/bridges/` re-export the real
implementations from `project/api/src/` and `project/web/src/`, so tests never
have to reach across folders directly.

## Setup

```bash
# First time, or after dependency changes:
cd project/web && npm install
cd ../api && npm install
```

## Scripts

Run from `project/web` (covers every test, jsdom):

| Script | What it runs |
|--------|--------------|
| `npm run test` | Full suite (`tests/**/*.test.ts` + `*.test.tsx`) |
| `npm run test:ismael` | Files under `tests/ismael/` |
| `npm run test:jason` | Files under `tests/jason/` |
| `npm run test:joey` | Files whose path contains `joey` (filename prefix) |
| `npm run test:jiasheng` | Files whose path contains `jiasheng` |

Run from `project/api` (covers the API tests only, node env):

| Script | What it runs |
|--------|--------------|
| `npm test` | All `tests/**/*.test.ts` and `tests/api/**/*.test.tsx` via the api Vitest config |

`project/course_planner/package.json` mirrors the per-owner scripts so the same
commands also work from this folder:

```bash
cd project/course_planner
npm run test           # uses ../vitest.config.ts via the web node_modules
npm run test:jason     # etc.
```

## Adding tests

- Put new files under your owner folder (`ismael/`, `jason/`) **or** under the
  topical `api/<area>/` folder, using the convention `<owner>.<topic>.test.ts`
  (or `.test.tsx`).
- If your test needs to exercise real API or web code, import it through a
  bridge under `project/course_planner/bridges/`. Add a new bridge module when
  none exists, rather than reaching directly into `project/api/src` or
  `project/web/src` from the test.
- Run `npm run test:<yourname>` to scope a run, or `npm run test` from
  `project/web` before merging.
