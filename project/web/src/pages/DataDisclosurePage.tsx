import { DataDisclosureContent } from "../components/DataDisclosureContent";
import { StaticInfoPageLayout } from "../components/StaticInfoPageLayout";

type DataDisclosurePageProps = {
  isLoggedIn?: boolean;
};

export function DataDisclosurePage({ isLoggedIn = false }: DataDisclosurePageProps) {
  return (
    <StaticInfoPageLayout roundPanelBottom>
      <h1 className="mb-4 text-center text-xl font-bold tracking-tight text-[var(--scu-text)] sm:text-2xl">
        Data Disclosure
      </h1>
      <div className="mx-auto mb-6 h-px w-12 bg-[var(--scu-red)]" aria-hidden />

      <DataDisclosureContent showDeleteDataLink={isLoggedIn} />
    </StaticInfoPageLayout>
  );
}
