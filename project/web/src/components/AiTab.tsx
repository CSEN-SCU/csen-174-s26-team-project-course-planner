import { useState } from "react";
import type { AiChatMessage, AiRecommendation } from "../types/domain";

const dayColumns = [
  { label: "Mon", code: "M" },
  { label: "Tue", code: "T" },
  { label: "Wed", code: "W" },
  { label: "Thu", code: "R" },
  { label: "Fri", code: "F" }
] as const;

function parseStartHour(timeRange: string) {
  const [start = "09:00"] = timeRange.split("-");
  const [hourText] = start.split(":");
  return Number(hourText);
}

function sortByStartTime(a: { time: string }, b: { time: string }) {
  return parseStartHour(a.time) - parseStartHour(b.time);
}

export function AiTab({
  plans,
  chatMessages,
  aiLabel,
  aiEnabled,
  onSendMessage,
  onAcceptPlan
}: {
  plans: AiRecommendation[];
  chatMessages: AiChatMessage[];
  aiLabel: string;
  aiEnabled: boolean;
  onSendMessage: (message: string) => void;
  onAcceptPlan: (planId: string) => void;
}) {
  const [draft, setDraft] = useState("");

  return (
    <article className="glass rounded-2xl p-5">
      <div className="mb-4 rounded-lg border border-sky-300/40 bg-sky-950/25 px-3 py-2 text-sm text-sky-100">
        AI model in use: <span className="font-semibold">{aiLabel}</span> {aiEnabled ? "(live)" : "(sample mode)"}
      </div>
      <div className="mt-4 rounded-xl border border-slate-700 bg-slate-900/30 p-4">
        <p className="mb-3 text-sm font-semibold text-slate-100">Ask the planner AI</p>
        <div className="max-h-56 space-y-2 overflow-auto pr-1">
          {chatMessages.length === 0 && (
            <p className="text-sm text-slate-300">Ask for advice like: "Give me an easier 3-course quarter with Tue/Thu focus."</p>
          )}
          {chatMessages.map((message) => (
            <div
              key={message.id}
              className={
                message.role === "assistant"
                  ? "rounded-lg bg-sky-950/30 px-3 py-2 text-sm text-sky-100"
                  : "rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-100"
              }
            >
              {message.content}
            </div>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && draft.trim()) {
                onSendMessage(draft.trim());
                setDraft("");
              }
            }}
            placeholder="Ask for schedule advice or generate a schedule..."
            className="w-full rounded-lg border border-slate-600 bg-slate-950/40 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-300"
          />
          <button
            onClick={() => {
              if (!draft.trim()) return;
              onSendMessage(draft.trim());
              setDraft("");
            }}
            className="rounded-lg border border-sky-300 px-3 py-2 text-sm font-semibold text-sky-200"
          >
            Send
          </button>
        </div>
      </div>
      <div className="mt-4 space-y-3">
        {plans.length === 0 && <p className="text-sm text-slate-300">Generate a preview plan to see proposed classes.</p>}
        {plans.map((plan) => (
          <div key={plan.id} className="rounded-xl border border-slate-700 bg-slate-900/30 p-4">
            <p className="font-semibold text-sky-100">{plan.title}</p>
            <p className="text-sm text-slate-300">{plan.rationale}</p>
            <div className="mt-3 overflow-auto rounded-lg border border-slate-700">
              <div className="grid min-w-[660px] grid-cols-5 gap-0">
                {dayColumns.map((day) => {
                  const dayItems = plan.items
                    .filter((item) => item.days.includes(day.code))
                    .sort(sortByStartTime);
                  return (
                    <div key={`${plan.id}-${day.code}`} className="border-r border-slate-700 last:border-r-0">
                      <div className="border-b border-slate-700 bg-slate-950/40 px-2 py-2 text-center text-xs font-semibold text-slate-200">
                        {day.label}
                      </div>
                      <div className="space-y-2 p-2">
                        {dayItems.length === 0 && <p className="text-[11px] text-slate-500">No class</p>}
                        {dayItems.map((item) => (
                          <div key={`${plan.id}-${day.code}-${item.courseCode}`} className="rounded-md bg-sky-950/30 px-2 py-2 text-[11px]">
                            <p className="font-semibold text-sky-100">{item.courseCode}</p>
                            <p className="text-slate-200">{item.time}</p>
                            <p className="text-slate-300">
                              Q {item.quality?.toFixed(1) ?? "0.0"} / D {item.difficulty?.toFixed(1) ?? "0.0"}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            <button
              onClick={() => onAcceptPlan(plan.id)}
              className="mt-3 rounded-lg border border-mint px-3 py-2 text-xs font-semibold text-mint"
            >
              Accept this plan
            </button>
          </div>
        ))}
      </div>
    </article>
  );
}

