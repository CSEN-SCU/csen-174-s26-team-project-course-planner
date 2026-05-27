export function BrandLink({ className = "" }: { className?: string }) {
  return (
    <a
      href="/"
      className={`flex items-center gap-1.5 no-underline transition hover:opacity-90 ${className}`}
    >
      <span className="text-2xl font-bold leading-none tracking-tight text-[var(--scu-red)]">
        SCU
      </span>
      <span className="text-sm font-medium leading-snug text-neutral-500">Course Planner</span>
    </a>
  );
}
