import type { ReactNode } from "react";

/** Matches left sidebar brand row height (logo + border below). */
export function PlannerColumnHeader({
  children,
  align = "start",
}: {
  children: ReactNode;
  align?: "start" | "end" | "between";
}) {
  const alignClass =
    align === "end"
      ? "justify-end"
      : align === "between"
        ? "justify-between"
        : "justify-start";

  return (
    <header
      className={`flex min-h-[4.5rem] shrink-0 items-center border-b border-neutral-200 bg-[var(--scu-white)] px-4 py-5 ${alignClass}`}
    >
      {children}
    </header>
  );
}
