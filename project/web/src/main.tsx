import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { bootstrapPlannerShellClass } from "./lib/shellBootstrap";
import { Root } from "./Root";

bootstrapPlannerShellClass();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
