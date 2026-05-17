import App from "./App";
import { DataDisclosurePage } from "./pages/DataDisclosurePage";

function normalizePath(pathname: string): string {
  const trimmed = pathname.replace(/\/+$/, "");
  return trimmed === "" ? "/" : trimmed;
}

export function Root() {
  const path = normalizePath(window.location.pathname);
  if (path === "/data-disclosure") {
    return <DataDisclosurePage />;
  }
  return <App />;
}
