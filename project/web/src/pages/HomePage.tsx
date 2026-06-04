import { useEffect, useState } from "react";
import { GoogleSignInButton } from "../components/GoogleSignInButton";
import { SiteFooter } from "../components/SiteFooter";
import { resetPageScroll } from "../lib/scroll";

const TAGLINE =
  "Build your upcoming SCU schedule, personalized with your major requirements and course preferences.";

export type HomePageProps = {
  externalAuthError?: string | null;
};

export function HomePage({ externalAuthError }: HomePageProps) {
  const [deleteDataNotice, setDeleteDataNotice] = useState<string | null>(null);

  useEffect(() => {
    resetPageScroll();
  }, []);

  useEffect(() => {
    try {
      const msg = sessionStorage.getItem("scu_delete_user_data_notice");
      if (msg) {
        setDeleteDataNotice(msg);
        sessionStorage.removeItem("scu_delete_user_data_notice");
      }
    } catch {
      /* ignore */
    }
  }, []);

  return (
    <div className="home-page flex min-h-dvh w-full max-w-full flex-col overflow-y-auto overflow-x-hidden">
      <main className="flex min-h-0 flex-1 flex-col items-center justify-center px-6 py-12">
        <div className="home-hero w-full max-w-lg text-center">
          <div className="home-brand mb-6" aria-label="SCU Course Planner">
            <span className="home-brand-scu">SCU</span>
            <span className="home-brand-planner">Course Planner</span>
          </div>

          <p className="home-tagline mx-auto mb-10 max-w-md text-base leading-relaxed text-neutral-600 sm:text-lg">
            {TAGLINE}
          </p>

          {deleteDataNotice && (
            <p
              role="status"
              className="mx-auto mb-4 max-w-sm rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
            >
              {deleteDataNotice}
            </p>
          )}

          {externalAuthError && (
            <p
              role="alert"
              className="mx-auto mb-4 max-w-xs rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              {externalAuthError}
            </p>
          )}

          <div className="flex flex-col items-center gap-4">
            <GoogleSignInButton />
          </div>
        </div>
      </main>

      <SiteFooter />
    </div>
  );
}
