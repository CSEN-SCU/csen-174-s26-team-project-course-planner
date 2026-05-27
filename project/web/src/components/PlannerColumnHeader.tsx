import type { ReactNode } from "react";

/** Matches left sidebar brand row height (logo + border below). */
export function PlannerColumnHeader({
  children,
  align = "start",
  variant = "brand",
}: {
  children: ReactNode;
  align?: "start" | "end" | "between";
  /** brand: logo / sign-out row; toolbar: tabs flush to the shared border */
  variant?: "brand" | "toolbar";
}) {
  const alignClass =
    align === "end"
      ? "justify-end"
      : align === "between"
        ? "justify-between"
        : "justify-start";

  const variantClass =
    variant === "toolbar"
      ? "items-end px-3 pb-0 pt-5"
      : "items-center px-4 py-5";

  return (
    <header
      className={`flex min-h-[4.5rem] shrink-0 border-b border-neutral-200 bg-[var(--scu-white)] ${variantClass} ${alignClass}`}
    >
      {children}
    </header>
  );
}
