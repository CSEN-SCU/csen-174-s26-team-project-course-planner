import { StaticInfoPageLayout } from "../components/StaticInfoPageLayout";

const DISCLOSURE_TEXT =
  "Please note: Data enterred into this website will be processed by Gemini models. Names and grades are truncated from uploaded academic progress reports, however any other information, including personaly identifiable information entered into the message box, will be sent and processed.";

export function DataDisclosurePage() {
  return (
    <StaticInfoPageLayout roundPanelBottom>
      <h1 className="mb-4 text-center text-xl font-bold tracking-tight text-[var(--scu-text)] sm:text-2xl">
        Data Disclosure
      </h1>
      <div className="mx-auto mb-6 h-px w-12 bg-[var(--scu-red)]" aria-hidden />
      <p className="text-center text-sm leading-relaxed text-neutral-600 sm:text-base sm:leading-7">
        {DISCLOSURE_TEXT}
      </p>
    </StaticInfoPageLayout>
  );
}
