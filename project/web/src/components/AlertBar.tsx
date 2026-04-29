export function AlertBar({ kind, message }: { kind: "loading" | "error"; message: string }) {
  if (kind === "loading") {
    return <div className="glass rounded-xl border border-sky-400/40 p-3 text-sm text-sky-100">{message}</div>;
  }
  return <div className="rounded-xl border border-rose-500/60 bg-rose-900/20 p-3 text-sm text-rose-100">{message}</div>;
}

