# How to run tests

Tests live under `project/tests/` in owner folders (`ismael/`, `jason/`, `joey/`, `jiasheng/`). Commands are defined in `project/web/package.json` because Vitest and frontend test dependencies are installed there.

From the repo root:

```bash
cd project/web
npm install   # first time or after dependency changes
```

## Scripts

Run these from **`project/web`** (same directory as `package.json`):

| Script | What it runs |
|--------|----------------|
| `npm run test` | Full suite: all files matching `project/tests/**/*.test.ts` and `**/*.test.tsx` |
| `npm run test:ismael` | Only `project/tests/ismael/` |
| `npm run test:jason` | Only `project/tests/jason/` |
| `npm run test:joey` | Only `project/tests/joey/` (no tests yet → exits successfully with `--passWithNoTests`) |
| `npm run test:jiasheng` | Only `project/tests/jiasheng/` (same as Joey until tests exist) |

## For Cursor / agents

- Use **`project/web`** as the working directory for `npm run test*` commands.
- Config file: `project/vitest.config.ts` (referenced by the npm scripts).

## Adding tests

Put new files under your owner folder, named `*.test.ts` or `*.test.tsx`, then run `npm run test:<yourname>` to scope the run, or `npm run test` before merging.
