import { useCallback, useLayoutEffect, useRef, type ReactNode } from "react";
import { BrandLink } from "./BrandLink";
import { SiteFooter } from "./SiteFooter";

type StaticInfoPageLayoutProps = {
  children: ReactNode;
  maxWidth?: "max-w-2xl" | "max-w-3xl";
  /** Round the panel bottom when content ends above the footer (data disclosure only). */
  roundPanelBottom?: boolean;
};

export function StaticInfoPageLayout({
  children,
  maxWidth = "max-w-2xl",
  roundPanelBottom = false,
}: StaticInfoPageLayoutProps) {
  const mainRef = useRef<HTMLElement>(null);
  const anchorRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelSurfaceRef = useRef<HTMLDivElement>(null);
  const headerRef = useRef<HTMLElement>(null);
  const footerWrapRef = useRef<HTMLDivElement>(null);

  const syncPanel = useCallback(() => {
    const anchor = anchorRef.current;
    const panel = panelRef.current;
    const panelSurface = panelSurfaceRef.current;
    const footerWrap = footerWrapRef.current;
    if (!anchor || !panel) return;

    const anchorTop = anchor.getBoundingClientRect().top;
    const headerBottom = headerRef.current?.getBoundingClientRect().bottom ?? anchorTop;
    const isTopClamped = anchorTop < headerBottom - 0.5;

    panel.style.top = `${Math.max(anchorTop, headerBottom)}px`;

    if (footerWrap) {
      const footerTop = footerWrap.getBoundingClientRect().top;
      panel.style.bottom = `${window.innerHeight - footerTop}px`;
    }

    if (panelSurface) {
      panelSurface.classList.toggle("rounded-t-lg", !isTopClamped);
      panelSurface.classList.toggle("rounded-t-none", isTopClamped);

      if (roundPanelBottom) {
        const article = anchor.parentElement?.querySelector("article");
        const articleBottom = article?.getBoundingClientRect().bottom ?? 0;
        const footerTop = footerWrap?.getBoundingClientRect().top ?? window.innerHeight;
        const isBottomClamped = articleBottom >= footerTop - 0.5;
        panelSurface.classList.toggle("rounded-b-lg", !isBottomClamped);
        panelSurface.classList.toggle("rounded-b-none", isBottomClamped);
      }
    }
  }, [roundPanelBottom]);

  useLayoutEffect(() => {
    syncPanel();
    const main = mainRef.current;
    if (!main) return;

    main.addEventListener("scroll", syncPanel, { passive: true });
    window.addEventListener("resize", syncPanel);

    const observer = new ResizeObserver(syncPanel);
    observer.observe(main);
    if (anchorRef.current) observer.observe(anchorRef.current);
    if (footerWrapRef.current) observer.observe(footerWrapRef.current);
    if (headerRef.current) observer.observe(headerRef.current);

    return () => {
      main.removeEventListener("scroll", syncPanel);
      window.removeEventListener("resize", syncPanel);
      observer.disconnect();
    };
  }, [syncPanel]);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[var(--scu-white)]">
      <header
        ref={headerRef}
        className="relative z-20 shrink-0 border-b border-neutral-200 border-l-4 border-l-[var(--scu-red)] bg-[var(--scu-white)] px-6 py-5 shadow-sm"
      >
        <BrandLink />
      </header>

      <div className="relative min-h-0 flex-1">
        <div
          ref={panelRef}
          aria-hidden
          className="pointer-events-none fixed left-0 right-0 z-[1] flex justify-center px-6"
        >
          <div
            ref={panelSurfaceRef}
            className={`h-full w-full rounded-t-lg rounded-b-none border border-neutral-200 border-l-4 border-l-[var(--scu-red)] bg-[var(--scu-gray)] shadow-sm ${maxWidth}`}
          />
        </div>

        <main ref={mainRef} className="relative z-10 h-full overflow-y-auto px-6 pb-8">
          <div className="pt-[5%]">
            <div ref={anchorRef} className="h-0 w-full" aria-hidden />
            <article className={`relative mx-auto w-full ${maxWidth} px-6 py-10 sm:px-10 sm:py-12`}>
              {children}
            </article>
          </div>
        </main>
      </div>

      <div ref={footerWrapRef} className="relative z-20 shrink-0 bg-white">
        <SiteFooter />
      </div>
    </div>
  );
}
