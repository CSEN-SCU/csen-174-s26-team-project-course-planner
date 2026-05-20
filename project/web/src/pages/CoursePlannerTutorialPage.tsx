import { StaticInfoPageLayout } from "../components/StaticInfoPageLayout";

const STEPS = [
  {
    number: 1,
    text: "Follow the Academic Progress Export Steps.",
    placeholder: (
      <a
        href="#/academic-progress-export-tutorial"
        className="text-sm font-semibold text-[var(--scu-red)] underline-offset-2 hover:underline"
      >
        Open Academic Progress Export Tutorial →
      </a>
    ),
  },
  {
    number: 2,
    text: "Use the chat feature.",
    placeholder: (
      <p className="text-sm text-neutral-500">Screenshot and instructions coming soon.</p>
    ),
  },
  {
    number: 3,
    text: "Build your schedule.",
    placeholder: (
      <p className="text-sm text-neutral-500">Screenshot and instructions coming soon.</p>
    ),
  },
] as const;

export function CoursePlannerTutorialPage() {
  return (
    <StaticInfoPageLayout maxWidth="max-w-3xl">
      <h1 className="mb-4 text-center text-xl font-bold tracking-tight text-[var(--scu-text)] sm:text-2xl">
        SCU Course Planner Tutorial
      </h1>
      <div className="mx-auto mb-8 h-px w-12 bg-[var(--scu-red)]" aria-hidden />

      <ol className="space-y-10">
        {STEPS.map((step) => (
          <li key={step.number} className="text-left">
            <h2 className="mb-3 text-sm font-semibold text-[var(--scu-text)] sm:text-base">
              <span className="mr-2 text-[var(--scu-red)]">Step {step.number}:</span>
              {step.text}
            </h2>
            <div className="flex min-h-[4.5rem] items-center justify-center rounded-md border border-neutral-200 bg-white px-5 py-4 shadow-sm">
              {step.placeholder}
            </div>
          </li>
        ))}
      </ol>

      <div className="mt-10 flex justify-center">
        <a
          href="/"
          className="text-sm font-semibold text-[var(--scu-red)] underline-offset-2 hover:underline"
        >
          Go to SCU Course Planner →
        </a>
      </div>
    </StaticInfoPageLayout>
  );
}
