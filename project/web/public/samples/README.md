# Sample academic progress

The "Try a sample file" button in the planner chat panel loads the file:

```
project/web/public/samples/sample-academic-progress.xlsx
```

served at runtime from `/<base>/samples/sample-academic-progress.xlsx`.

## Replacing the file

`sample-academic-progress.xlsx` is a real SCU Workday "Academic Progress"
export used as a demo. To swap it, drop in a different Workday `.xlsx` export
and keep the **exact same file name**:

```
sample-academic-progress.xlsx
```

No code changes are needed after replacing the file — the filename and location
are wired in `project/web/src/lib/sampleAcademicProgress.ts`.
