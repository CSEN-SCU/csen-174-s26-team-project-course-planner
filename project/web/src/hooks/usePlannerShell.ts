import { useLayoutEffect } from "react";
import { resetPageScroll } from "../lib/scroll";

const HTML_CLASS = "planner-shell";

/**
 * Lock the document and reset scroll for full-screen planner views.
 * No effect cleanup — avoids React StrictMode briefly unlocking scroll between remounts.
 */
export function usePlannerShell(active: boolean): void {
  useLayoutEffect(() => {
    if (!active) {
      document.documentElement.classList.remove(HTML_CLASS);
      return;
    }
    document.documentElement.classList.add(HTML_CLASS);
    resetPageScroll();
  }, [active]);

  useLayoutEffect(() => {
    if (!active) return;
    resetPageScroll();
    let inner = 0;
    const outer = requestAnimationFrame(() => {
      resetPageScroll();
      inner = requestAnimationFrame(resetPageScroll);
    });
    return () => {
      cancelAnimationFrame(outer);
      cancelAnimationFrame(inner);
    };
  }, [active]);
}
