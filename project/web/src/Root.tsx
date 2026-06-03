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
import { AuthLoadingPage } from "./pages/AuthLoadingPage";
import { HomePage } from "./pages/HomePage";
import { SignOutLoadingPage } from "./pages/SignOutLoadingPage";
import { resetPageScroll } from "./lib/scroll";
import { useDeleteUserDataModal } from "./hooks/useDeleteUserDataModal";

export function Root() {
  const [route, setRoute] = useState(resolveClientRoute);
  const [demoMode, setDemoMode] = useState(false);
  const { userId, googleAuthError, googleAuthPending, signOutPending, signOut } = useAuth();
  const { openDeleteModal, deleteModal } = useDeleteUserDataModal(userId);

  const isInfoRoute =
    route === DATA_DISCLOSURE_PATH ||
    route === ACADEMIC_PROGRESS_TUTORIAL_PATH ||
    route === COURSE_PLANNER_TUTORIAL_PATH;

  // A real sign-in always supersedes the guest demo.
  useEffect(() => {
    if (userId && demoMode) setDemoMode(false);
  }, [userId, demoMode]);

  usePlannerShell(
    Boolean(userId) || demoMode || googleAuthPending || signOutPending || isInfoRoute,
  );

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
    if (!userId) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("delete-user-data") !== "1") return;
    openDeleteModal();
    params.delete("delete-user-data");
    const q = params.toString();
    window.history.replaceState({}, document.title, q ? `?${q}` : window.location.pathname);
  }, [userId, openDeleteModal]);

  useEffect(() => {
    const sync = () => setRoute(resolveClientRoute());
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, []);

  const chromeProps = {
    userId,
    onSignOut: userId ? signOut : undefined,
    onDeleteUserData: userId ? openDeleteModal : undefined,
  };

  if (signOutPending) {
    return <SignOutLoadingPage />;
  }

  if (route === DATA_DISCLOSURE_PATH) {
    return (
      <>
        {deleteModal}
        <DataDisclosurePage {...chromeProps} />
      </>
    );
  }
  if (route === ACADEMIC_PROGRESS_TUTORIAL_PATH) {
    return (
      <>
        {deleteModal}
        <AcademicProgressExportTutorialPage {...chromeProps} />
      </>
    );
  }
  if (route === COURSE_PLANNER_TUTORIAL_PATH) {
    return (
      <>
        {deleteModal}
        <CoursePlannerTutorialPage {...chromeProps} />
      </>
    );
  }

  if (!userId) {
    if (googleAuthPending) {
      return <AuthLoadingPage />;
    }
    if (demoMode) {
      return (
        <div className="planner-app-root">
          <App userId="" onSignOut={() => setDemoMode(false)} demoMode />
        </div>
      );
    }
    return (
      <HomePage
        externalAuthError={googleAuthError}
        onTryDemo={() => setDemoMode(true)}
      />
    );
  }

  return (
    <>
      {deleteModal}
      <div className="planner-app-root">
        <App userId={userId} onSignOut={signOut} onDeleteUserData={openDeleteModal} />
      </div>
    </>
  );
}
