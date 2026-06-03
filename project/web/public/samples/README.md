# Sample academic progress (demo)

The demo button on the login page and the "Try a sample file" button inside the
planner both load the file:

```
project/web/public/samples/sample-academic-progress.xlsx
```

served at runtime from `/<base>/samples/sample-academic-progress.xlsx`.

## Replace the placeholder

`sample-academic-progress.xlsx` in this folder is a **placeholder** and is not a
valid Workday export yet. Replace it with a real SCU Workday "Academic Progress"
export (`.xlsx`), keeping the **exact same file name**:

```
sample-academic-progress.xlsx
```

No code changes are needed after replacing the file — the filename and location
are wired in `project/web/src/lib/sampleAcademicProgress.ts`.
