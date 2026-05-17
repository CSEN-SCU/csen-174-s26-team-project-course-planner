export function BrandLink({ className = "" }: { className?: string }) {
  return (
    <a
      href="/"
      className={`inline-flex items-baseline gap-1 no-underline transition hover:opacity-90 ${className}`}
    >
      <span className="text-2xl font-bold tracking-tight text-[var(--scu-red)]">SCU</span>
      <span className="text-sm font-medium text-neutral-500">Course Planner</span>
    </a>
  );
}
