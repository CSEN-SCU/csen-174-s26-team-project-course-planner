export function AppHeader({ onResetDemo, showReset }: { onResetDemo: () => void; showReset: boolean }) {
  return (
    <header className="glass rounded-3xl p-6 shadow-glow">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.25em] text-sky-300">Bronco Plan Prototype</p>
          <h1 className="mt-2 text-4xl font-bold text-white md:text-5xl">Schedule Smarter, Not Harder</h1>
          <p className="mt-3 max-w-3xl text-slate-200">
            An SCU course planner for undergrads. Upload your transcript, explore only eligible classes, compare quality versus
            difficulty, and generate schedule options without juggling Workday tabs.
          </p>
        </div>
        {showReset && (
          <button
            onClick={onResetDemo}
            className="rounded-xl border border-rose-400/60 bg-rose-900/20 px-4 py-2 text-sm font-semibold text-rose-100 hover:bg-rose-900/35"
          >
            Reset demo
          </button>
        )}
      </div>
    </header>
  );
}

