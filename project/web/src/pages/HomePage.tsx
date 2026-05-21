import { GoogleSignInButton } from "../components/GoogleSignInButton";
import { SiteFooter } from "../components/SiteFooter";

const TAGLINE =
  "Build your next-quarter schedule from your transcript and course data — personalized recommendations without the Workday maze.";

export type HomePageProps = {
  externalAuthError?: string | null;
  authPending?: boolean;
};

export function HomePage({ externalAuthError, authPending }: HomePageProps) {
  return (
    <div className="home-page flex min-h-screen w-screen flex-col overflow-hidden">
      <main className="flex min-h-0 flex-1 flex-col items-center justify-center px-6 py-12">
        <div className="home-hero w-full max-w-lg text-center">
          <div className="home-brand mb-6" aria-label="SCU Course Planner">
            <span className="home-brand-scu">SCU</span>
            <span className="home-brand-planner">Course Planner</span>
          </div>

          <p className="home-tagline mx-auto mb-10 max-w-md text-base leading-relaxed text-neutral-600 sm:text-lg">
            {TAGLINE}
          </p>

          {externalAuthError && (
            <p
              role="alert"
              className="mx-auto mb-4 max-w-xs rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              {externalAuthError}
            </p>
          )}

          <div className="flex flex-col items-center gap-4">
            {authPending ? (
              <p className="text-sm text-neutral-500">Signing in with Google…</p>
            ) : (
              <GoogleSignInButton />
            )}
            <p className="text-xs text-neutral-500">
              Sign in with Google to save plans and build your schedule.
            </p>
          </div>
        </div>
      </main>

      <SiteFooter />
    </div>
  );
}
