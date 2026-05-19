import { useEffect, useState } from "react";
import App from "./App";
import { DataDisclosurePage } from "./pages/DataDisclosurePage";

function normalizePath(pathname: string): string {
  const trimmed = pathname.replace(/\/+$/, "");
  return trimmed === "" ? "/" : trimmed;
}

/** Client route: hash works on static hosts (Render) without server rewrites. */
function currentRoute(): string {
  const hash = window.location.hash.replace(/^#\/?/, "");
  if (hash === "data-disclosure") {
    return "/data-disclosure";
  }
  return normalizePath(window.location.pathname);
}

export function Root() {
  const [route, setRoute] = useState(currentRoute);

  useEffect(() => {
    const sync = () => setRoute(currentRoute());
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, []);

  if (route === "/data-disclosure") {
    return <DataDisclosurePage />;
  }
  return <App />;
}
