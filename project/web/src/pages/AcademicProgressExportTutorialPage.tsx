import { StaticInfoPageLayout } from "../components/StaticInfoPageLayout";
import step1Img from "../img/Workday_tutorial_1.png";
import step2Img from "../img/Workday_tutorial_2.png";
import step3Img from "../img/Workday_tutorial_3.png";
import step4Img from "../img/Workday_tutorial_4.png";
import step5Img from "../img/Workday_tutorial_5.png";

const STEPS = [
  {
    number: 1,
    text: "After logging in to Workday, click the Academics button",
    image: step1Img,
    alt: "A screenshot of the Workday homepage, with the Academics button highlighted",
  },
  {
    number: 2,
    text: "Click on the View My Academic Progress button",
    image: step2Img,
    alt: "A screenshot of the Workday academics page, with the View My Academic Progress button highlighted",
  },
  {
    number: 3,
    text: "Click OK",
    image: step3Img,
    alt: "A screenshot of the View My Academic Progress page, with the OK button highlighted",
  },
  {
    number: 4,
    text: "Click the small box with an X icon",
    image: step4Img,
    alt: "A screenshot of the View My Academic Progress page, with the small box with an X icon highlighted",
  },
  {
    number: 5,
    text: "Click Download",
    image: step5Img,
    alt: "A screenshot of the Export Document dialog, with the Download button highlighted",
  },
  {
    number: 6,
    text: "Upload this file into SCU Course Planner to receive more tailored advice",
  },
] as const;

export function AcademicProgressExportTutorialPage() {
  return (
    <StaticInfoPageLayout maxWidth="max-w-3xl">
      <h1 className="mb-4 text-center text-xl font-bold tracking-tight text-[var(--scu-text)] sm:text-2xl">
        How to Export Academic Progress Reports
      </h1>
      <div className="mx-auto mb-8 h-px w-12 bg-[var(--scu-red)]" aria-hidden />

      <ol className="space-y-10">
        {STEPS.map((step) => (
          <li key={step.number} className="text-left">
            <h2 className="mb-3 text-sm font-semibold text-[var(--scu-text)] sm:text-base">
              <span className="mr-2 text-[var(--scu-red)]">Step {step.number}:</span>
              {step.text}
            </h2>
            {"image" in step && step.image ? (
              <img
                src={step.image}
                alt={step.alt}
                className="w-full rounded-md border border-neutral-200 bg-white shadow-sm"
                loading="lazy"
              />
            ) : (
              <div className="flex min-h-[4.5rem] items-center justify-center rounded-md border border-neutral-200 bg-white px-5 py-4 shadow-sm">
                <a
                  href="/"
                  className="text-sm font-semibold text-[var(--scu-red)] underline-offset-2 hover:underline"
                >
                  Go to SCU Course Planner →
                </a>
              </div>
            )}
          </li>
        ))}
      </ol>
    </StaticInfoPageLayout>
  );
}
