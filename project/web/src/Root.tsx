import { useEffect, useLayoutEffect, useState } from "react";
import App from "./App";
import { useAuth } from "./hooks/useAuth";
import { usePlannerShell } from "./hooks/usePlannerShell";
import {
  ACADEMIC_PROGRESS_TUTORIAL_PATH,
  COURSE_PLANNER_TUTORIAL_PATH,
  DATA_DISCLOSURE_PATH,
  resolveClientRoute,
} from "./lib/routes";
import { AcademicProgressExportTutorialPage } from "./pages/AcademicProgressExportTutorialPage";
import { CoursePlannerTutorialPage } from "./pages/CoursePlannerTutorialPage";
import { DataDisclosurePage } from "./pages/DataDisclosurePage";
import { HomePage } from "./pages/HomePage";
import { resetPageScroll } from "./lib/scroll";

export function Root() {
  const [route, setRoute] = useState(resolveClientRoute);
  const { userId, googleAuthError, googleAuthPending, signOut } = useAuth();

  const isInfoRoute =
    route === DATA_DISCLOSURE_PATH ||
    route === ACADEMIC_PROGRESS_TUTORIAL_PATH ||
    route === COURSE_PLANNER_TUTORIAL_PATH;

  usePlannerShell(Boolean(userId) || isInfoRoute);

  useLayoutEffect(() => {
    resetPageScroll();
  }, [route, userId]);

  useEffect(() => {
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) resetPageScroll();
    };
    window.addEventListener("pageshow", onPageShow);
    return () => window.removeEventListener("pageshow", onPageShow);
  }, []);

  useEffect(() => {
    const sync = () => setRoute(resolveClientRoute());
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, []);

  if (route === DATA_DISCLOSURE_PATH) {
    return <DataDisclosurePage isLoggedIn={Boolean(userId)} />;
  }
  if (route === ACADEMIC_PROGRESS_TUTORIAL_PATH) {
    return <AcademicProgressExportTutorialPage />;
  }
  if (route === COURSE_PLANNER_TUTORIAL_PATH) {
    return <CoursePlannerTutorialPage />;
  }

  if (!userId) {
    return (
      <HomePage externalAuthError={googleAuthError} authPending={googleAuthPending} />
    );
  }

  return (
    <div className="planner-app-root">
      <App userId={userId} onSignOut={signOut} />
    </div>
  );
}
