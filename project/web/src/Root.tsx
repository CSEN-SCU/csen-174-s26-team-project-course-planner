import { useEffect, useState } from "react";
import App from "./App";
import { useAuth } from "./hooks/useAuth";
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

export function Root() {
  const [route, setRoute] = useState(resolveClientRoute);
  const { userId, googleAuthError, googleAuthPending, signOut } = useAuth();

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
    return <DataDisclosurePage />;
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

  return <App userId={userId} onSignOut={signOut} />;
}
