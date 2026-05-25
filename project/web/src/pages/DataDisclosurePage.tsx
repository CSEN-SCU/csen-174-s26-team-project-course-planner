import { DataDisclosureContent } from "../components/DataDisclosureContent";
import { StaticInfoPageLayout } from "../components/StaticInfoPageLayout";

export function DataDisclosurePage() {
  return (
    <StaticInfoPageLayout roundPanelBottom>
      <h1 className="mb-4 text-center text-xl font-bold tracking-tight text-[var(--scu-text)] sm:text-2xl">
        Data Disclosure
      </h1>
      <div className="mx-auto mb-6 h-px w-12 bg-[var(--scu-red)]" aria-hidden />

      <DataDisclosureContent />
    </StaticInfoPageLayout>
  );
}
