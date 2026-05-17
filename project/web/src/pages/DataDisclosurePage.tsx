import { BrandLink } from "../components/BrandLink";
import { SiteFooter } from "../components/SiteFooter";

const DISCLOSURE_TEXT =
  "Please note: Data enterred into this website will be processed by Gemini models. Names and grades are truncated from uploaded academic progress reports, however any other information, including personaly identifiable information entered into the message box, will be sent and processed.";

export function DataDisclosurePage() {
  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[var(--scu-white)]">
      <header className="shrink-0 border-b border-neutral-200 border-l-4 border-l-[var(--scu-red)] bg-[var(--scu-white)] px-6 py-5 shadow-sm">
        <BrandLink />
      </header>

      <main className="flex min-h-0 flex-1 justify-start overflow-y-auto px-6 pt-[5%] pb-8">
        <article className="mx-auto w-full max-w-2xl rounded-lg border border-neutral-200 border-l-4 border-l-[var(--scu-red)] bg-[var(--scu-gray)] px-8 py-10 text-center shadow-sm sm:px-10 sm:py-12">
          <h1 className="mb-4 text-xl font-bold tracking-tight text-[var(--scu-text)] sm:text-2xl">
            Data Disclosure
          </h1>
          <div className="mx-auto mb-6 h-px w-12 bg-[var(--scu-red)]" aria-hidden />
          <p className="text-sm leading-relaxed text-neutral-600 sm:text-base sm:leading-7">
            {DISCLOSURE_TEXT}
          </p>
        </article>
      </main>

      <SiteFooter />
    </div>
  );
}
