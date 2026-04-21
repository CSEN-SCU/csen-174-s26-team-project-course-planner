import type { AiRecommendation } from "../types/domain";

export function AiTab({
  plans,
  onRecommend,
  onComplete
}: {
  plans: AiRecommendation[];
  onRecommend: () => void;
  onComplete: () => void;
}) {
  return (
    <article className="glass rounded-2xl p-5">
      <div className="flex flex-wrap gap-3">
        <button onClick={onRecommend} className="rounded-lg bg-sky-300 px-4 py-2 text-sm font-semibold text-slate-900">
          Recommend schedule
        </button>
        <button onClick={onComplete} className="rounded-lg border border-mint px-4 py-2 text-sm font-semibold text-mint">
          Complete my schedule
        </button>
      </div>
      <div className="mt-4 space-y-3">
        {plans.length === 0 && <p className="text-sm text-slate-300">Run an AI action to generate plan options.</p>}
        {plans.map((plan) => (
          <div key={plan.id} className="rounded-xl border border-slate-700 bg-slate-900/30 p-4">
            <p className="font-semibold text-sky-100">{plan.title}</p>
            <p className="text-sm text-slate-300">{plan.rationale}</p>
          </div>
        ))}
      </div>
    </article>
  );
}

