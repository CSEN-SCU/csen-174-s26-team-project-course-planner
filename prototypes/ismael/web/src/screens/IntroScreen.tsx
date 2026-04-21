export function IntroScreen({
  uploadName,
  onUploadNameChange,
  onTrySample,
  onParseUpload
}: {
  uploadName: string;
  onUploadNameChange: (next: string) => void;
  onTrySample: () => void;
  onParseUpload: () => void;
}) {
  return (
    <section className="grid gap-6 md:grid-cols-[1.1fr_1fr]">
      <article className="glass rounded-3xl p-6">
        <h2 className="text-2xl text-white">What this app does</h2>
        <p className="mt-2 text-slate-200">
          Helps SCU students build better schedules by combining transcript progress, requirement coverage, and teaching quality signals.
        </p>
        <ul className="mt-4 list-disc space-y-2 pl-5 text-slate-100">
          <li>For SCU undergraduates planning next quarter.</li>
          <li>Solves confusing tool-hopping and unclear course tradeoffs.</li>
          <li>How to use: upload transcript, choose priorities, add sections, export.</li>
        </ul>
      </article>
      <article className="glass rounded-3xl p-6">
        <h3 className="text-xl font-semibold text-white">Start your planning flow</h3>
        <div className="mt-4 flex flex-col gap-3">
          <button onClick={onTrySample} className="rounded-xl bg-sky-300 px-4 py-3 font-semibold text-slate-900 transition hover:bg-sky-200">
            Try with sample transcript
          </button>
          <label className="rounded-xl border border-slate-400/40 bg-slate-900/30 px-4 py-3 text-sm text-slate-200">
            Upload transcript
            <input
              className="mt-2 block w-full text-xs"
              type="file"
              onChange={(event) => {
                const file = event.target.files?.[0];
                onUploadNameChange(file?.name ?? "");
              }}
            />
          </label>
          <button
            onClick={onParseUpload}
            className="rounded-xl border border-mint/70 bg-mint/15 px-4 py-3 font-semibold text-mint transition hover:bg-mint/25"
          >
            Parse uploaded transcript {uploadName ? `(${uploadName})` : ""}
          </button>
        </div>
      </article>
    </section>
  );
}

