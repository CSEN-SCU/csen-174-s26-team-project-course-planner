# How to run tests

All tests live under **`project/tests/`**. CI runs both the Vitest suite and pytest from `project/`.

## Layout

```
project/tests/
├── *.py                       Python: agents, API, schedule, memory, security
├── app/                       React component tests (Vitest + jsdom)
├── api/                       FastAPI-adjacent Vitest tests (Joey course API, DB utils)
├── ismael/                    React a11y / component tests
└── jason/                     Planning behavior + AI fallback tests
```

Bridge modules in `project/course_planner/bridges/` let some Vitest tests import
stub Express/Prisma code or re-export real React components without reaching
across folders directly.

## Setup

```bash
cd project && npm ci
pip install -r requirements.txt          # from project/ (or project/api/requirements.txt shim)
```

## Scripts (from `project/`)

| Script | What it runs |
|--------|--------------|
| `npm test` | Full Vitest suite |
| `npm run test:pytest` | `python3 -m pytest tests/` |
| `npm run test:ismael` | `tests/ismael/` |
| `npm run test:jason` | `tests/jason/` |
| `npm run test:joey` | `tests/api/` |

Frontend dev server (separate terminal): `cd project/web && npm run dev`.

## Adding tests

- **Python:** add `test_*.py` next to related tests; use `project/tests/conftest.py` fixtures.
- **Vitest:** put files under your owner folder or `tests/app/`, named `*.test.ts` / `*.test.tsx`.
- Run `npm test` and `npm run test:pytest` before merging.
