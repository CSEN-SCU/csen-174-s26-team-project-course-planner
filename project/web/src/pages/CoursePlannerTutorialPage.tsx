import { StaticInfoPageLayout } from "../components/StaticInfoPageLayout";
import { ACADEMIC_PROGRESS_TUTORIAL_HREF } from "../lib/routes";
import step1Img from "../img/Tutorial1.png";
import step2Img from "../img/Tutorial2.png";
import step3Img from "../img/Tutorial3.png";
import step4Img from "../img/Tutorial4.png";
import step5Img from "../img/Tutorial5.png";
import step6Img from "../img/Tutorial6.png";
import step7Img from "../img/Tutorial7.png";
import step8Img from "../img/Tutorial8.png";

const STEPS = [
  {
    number: 1,
    text: "Sign in with your Google account",
    image: step1Img,
    imageWidth: 1920,
    imageHeight: 1043,
    alt: "SCU Course Planner landing page with the Continue with Google button highlighted",
  },
  {
    number: 2,
    text: "Read through the welcome pages carefully, clicking next to continue",
    image: step2Img,
    imageWidth: 1920,
    imageHeight: 1040,
    alt: "Welcome carousel overlay with the Next button highlighted",
  },
  {
    number: 3,
    text: "Upload your Academic Progress Report using the paperclip icon, or drag and drop it into the chat",
    image: step3Img,
    imageWidth: 1920,
    imageHeight: 1040,
    alt: "Planner dashboard with the chat attachment paperclip icon highlighted",
    link: {
      href: ACADEMIC_PROGRESS_TUTORIAL_HREF,
      label: "Academic Progress Export Tutorial →",
    },
  },
  {
    number: 4,
    text: "Write your courses preferences in the chat, such as difficulty, quality, time, or day of the week, then click Send",
    image: step4Img,
    imageWidth: 1920,
    imageHeight: 1040,
    alt: "Chat panel with a  highlighted message box containing a scheduling preference typed out",
  },
  {
    number: 5,
    text: "Carefully review your generated schedule, it is only intended to be a starting point. Modify it by either clicking on an open spot to add a new course, clicking on a course to change sections, clicking on the small X icon to remove it, or clicking Browse Courses to view a full ist of courses",
    image: step5Img,
    imageWidth: 1920,
    imageHeight: 1042,
    alt: "Weekly calendar with Browse Courses, a course section, and an empty slot menu highlighted",
  },
  {
    number: 6,
    text: "Use the left pane to manage your saved schedules. Use the Save, Clear, and New buttons and find previously saved schedules below in Past Sessions",
    image: step6Img,
    imageWidth: 1920,
    imageHeight: 1041,
    alt: "Left sidebar with Save schedule, Clear schedule, New plan, and Past Sessions highlighted",
  },
  {
    number: 7,
    text: "Open the Four-Year Plan tab to view your course plans for your entire degree",
    image: step7Img,
    imageWidth: 1920,
    imageHeight: 1041,
    alt: "Planner with the Four-Year Plan tab highlighted",
  },
  {
    number: 8,
    text: "The Four-Year Plan page will initially be filled with your courses up as layed out in you Academic Progress Report. Click the Generate Plan button to recommend courses into the future and download it using the Export to Spreadsheet button. Similar to the Course Schedules, these generated plans should be only be considered a starting point for you to work off of",
    image: step8Img,
    imageWidth: 1920,
    imageHeight: 1041,
    alt: "Four-year plan view with Generate Plan and Export to Spreadsheet buttons highlighted",
  },
] as const;

type TutorialScreenshotProps = {
  src: string;
  alt: string;
  width: number;
  height: number;
};

function TutorialScreenshot({ src, alt, width, height }: TutorialScreenshotProps) {
  return (
    <div
      className="w-full overflow-hidden rounded-md border border-neutral-200 bg-white shadow-sm"
      style={{ aspectRatio: `${width} / ${height}` }}
    >
      <img
        src={src}
        alt={alt}
        width={width}
        height={height}
        className="h-full w-full object-contain"
        loading="lazy"
        decoding="async"
      />
    </div>
  );
}

type TutorialPageChromeProps = {
  userId?: string | null;
  onSignOut?: () => void;
  onDeleteUserData?: () => void;
};

export function CoursePlannerTutorialPage({
  userId = null,
  onSignOut,
  onDeleteUserData,
}: TutorialPageChromeProps = {}) {
  return (
    <StaticInfoPageLayout
      maxWidth="max-w-3xl"
      userId={userId}
      onSignOut={onSignOut}
      onDeleteUserData={onDeleteUserData}
    >
      <h1 className="mb-4 text-center text-xl font-bold tracking-tight text-[var(--scu-text)] sm:text-2xl">
        SCU Course Planner Tutorial
      </h1>
      <div className="mx-auto mb-8 h-px w-12 bg-[var(--scu-red)]" aria-hidden />

      <p className="mb-10 text-left text-sm leading-relaxed text-neutral-600 sm:text-base">
        Welcome to SCU Course Planner! This tutorial will walk you through the basic functionality of this web app. Please note, the generated recommnedations of SCU Course Planner are only intended as a starting point to save you time in picking classes and may be contain errors. You should use them as a starting point to refine them based on your needs and desires. Please make sure to check any recommendations before relying on them.
      </p>

      <ol className="space-y-10">
        {STEPS.map((step) => (
          <li key={step.number} className="text-left">
            <h2 className="mb-3 text-sm font-semibold text-[var(--scu-text)] sm:text-base">
              <span className="mr-2 text-[var(--scu-red)]">Step {step.number}:</span>
              {step.text}
            </h2>
            {"link" in step && step.link ? (
              <div className="mb-3 flex justify-center">
                <a
                  href={step.link.href}
                  className="text-sm font-semibold text-[var(--scu-red)] underline-offset-2 hover:underline"
                >
                  {step.link.label}
                </a>
              </div>
            ) : null}
            <TutorialScreenshot
              src={step.image}
              alt={step.alt}
              width={step.imageWidth}
              height={step.imageHeight}
            />
          </li>
        ))}
      </ol>

      <div className="mt-6 flex justify-center">
        <p className="mt-10 text-left text-sm leading-relaxed text-neutral-600 sm:text-base">
          We hope you enjoy SCU Course Planner!
        </p>
      </div>

      <div className="mt-6 flex justify-center">
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
