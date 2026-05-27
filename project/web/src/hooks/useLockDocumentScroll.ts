import { useEffect } from "react";
import { resetPageScroll } from "../lib/scroll";

/**
 * Prevent the document from scrolling behind a full-viewport app shell.
 * Fixes clipped headers/sidebars after refresh (Safari/Chrome restore scroll).
 */
export function useLockDocumentScroll(active: boolean): void {
  useEffect(() => {
    if (!active) return;

    const html = document.documentElement;
    const body = document.body;
    const prevHtmlOverflow = html.style.overflow;
    const prevBodyOverflow = body.style.overflow;
    const prevBodyPosition = body.style.position;
    const prevBodyWidth = body.style.width;
    const prevBodyTop = body.style.top;
    const prevBodyLeft = body.style.left;

    const apply = () => {
      resetPageScroll();
      html.style.overflow = "hidden";
      body.style.overflow = "hidden";
      body.style.position = "fixed";
      body.style.width = "100%";
      body.style.top = "0";
      body.style.left = "0";
    };

    apply();
    const raf = requestAnimationFrame(() => {
      apply();
      requestAnimationFrame(apply);
    });

    const onResize = () => apply();
    window.addEventListener("resize", onResize);
    const vv = window.visualViewport;
    vv?.addEventListener("resize", onResize);
    vv?.addEventListener("scroll", onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      vv?.removeEventListener("resize", onResize);
      vv?.removeEventListener("scroll", onResize);
      html.style.overflow = prevHtmlOverflow;
      body.style.overflow = prevBodyOverflow;
      body.style.position = prevBodyPosition;
      body.style.width = prevBodyWidth;
      body.style.top = prevBodyTop;
      body.style.left = prevBodyLeft;
      resetPageScroll();
    };
  }, [active]);
}
