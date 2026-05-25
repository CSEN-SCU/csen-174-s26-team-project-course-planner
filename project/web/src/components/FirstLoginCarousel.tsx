import { useEffect, useState } from "react";
import { DataDisclosureContent } from "./DataDisclosureContent";
import {
  ACADEMIC_PROGRESS_TUTORIAL_HREF,
  COURSE_PLANNER_TUTORIAL_HREF,
} from "../lib/routes";

type FirstLoginCarouselProps = {
  open: boolean;
  onFinish: () => void;
};

const TOTAL_STEPS = 4;

export function FirstLoginCarousel({ open, onFinish }: FirstLoginCarouselProps) {
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (open) setStep(0);
  }, [open]);

  if (!open) return null;

  const isLastStep = step === TOTAL_STEPS - 1;
  const title = [
    "Welcome to SCU Course Planner",
    "Data Disclosure",
    "Academic Progress Export",
    "SCU Course Planner Tutorial",
  ][step];

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-[rgba(18,18,18,0.62)] px-4 py-6 backdrop-blur-sm">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="first-login-carousel-title"
        className="relative flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl border border-white/70 bg-white shadow-2xl"
      >
        <div className="shrink-0 bg-[var(--scu-bronco-red)] px-6 py-4 sm:px-8">
          <h1
            id="first-login-carousel-title"
            className="text-center text-xl font-bold tracking-tight text-white sm:text-2xl"
          >
            {title}
          </h1>
        </div>

        <div className="min-h-[24rem] overflow-y-auto px-6 py-8 sm:px-8">
          {step === 0 && (
            <div className="flex min-h-[18rem] items-center justify-center">
              <p className="max-w-xl text-center text-lg leading-8 text-neutral-700">
                Welcome to SCU Course Planner, please read through the following information before
                you get started.
              </p>
            </div>
          )}

          {step === 1 && (
            <div className="[&_h2]:text-sm [&_li]:text-sm [&_p]:text-sm">
              <DataDisclosureContent showDeleteDataLink />
            </div>
          )}

          {step === 2 && (
            <LinkStep
              body="You will need to export your Academic Progress Report from Workday so the planner can understand your remaining requirements. Click the button below to read a tutorial on how to export if you need instructions on how to do it."
              href={ACADEMIC_PROGRESS_TUTORIAL_HREF}
              linkText="Open Academic Progress Export Tutorial"
            />
          )}

          {step === 3 && (
            <LinkStep
              body="Learn the basic workflow for uploading progress, chatting with the planner, and building a schedule."
              href={COURSE_PLANNER_TUTORIAL_HREF}
              linkText="Open SCU Course Planner Tutorial"
            />
          )}
        </div>

        <div className="flex items-center justify-between gap-4 border-t border-neutral-100 bg-neutral-50 px-6 py-4 sm:px-8">
          <div className="flex gap-2" aria-label="Carousel progress">
            {Array.from({ length: TOTAL_STEPS }).map((_, index) => (
              <span
                key={index}
                className={`h-2.5 rounded-full transition-all ${
                  index === step ? "w-8 bg-[var(--scu-red)]" : "w-2.5 bg-neutral-300"
                }`}
              />
            ))}
          </div>

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setStep((current) => Math.max(0, current - 1))}
              disabled={step === 0}
              className="rounded-full border border-neutral-300 px-5 py-2 text-sm font-semibold text-neutral-600 transition hover:border-neutral-400 hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              Back
            </button>
            <button
              type="button"
              onClick={() => {
                if (isLastStep) {
                  onFinish();
                } else {
                  setStep((current) => Math.min(TOTAL_STEPS - 1, current + 1));
                }
              }}
              className="rounded-full bg-[var(--scu-red)] px-6 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[var(--scu-dark-red)]"
            >
              {isLastStep ? "Start" : "Next"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function LinkStep({
  body,
  href,
  linkText,
}: {
  body: string;
  href: string;
  linkText: string;
}) {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center justify-center py-10 text-center">
      <p className="text-lg leading-8 text-neutral-700">{body}</p>
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="mt-8 inline-flex rounded-full bg-[var(--scu-red)] px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[var(--scu-dark-red)]"
      >
        {linkText}
      </a>
    </div>
  );
}
