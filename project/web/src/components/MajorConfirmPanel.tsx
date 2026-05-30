import { useEffect, useState } from "react";
import { confirmStudentMajor, listMajors, type MajorListEntry } from "../api/client";

export type MajorDetection = {
  major_id?: string | null;
  name?: string | null;
  confidence?: string;
  message?: string;
  needs_confirmation?: boolean;
  candidates?: { major_id: string; name: string; score?: number }[];
};

export type MajorConfirmPanelProps = {
  userId: string;
  detection: MajorDetection | null;
  selectedMajorId: string | null;
  majorConfirmed: boolean;
  onSelectMajor: (majorId: string, name: string) => void;
  onConfirmed: () => void;
  onRequestChange?: () => void;
};

export function MajorConfirmPanel({
  userId,
  detection,
  selectedMajorId,
  majorConfirmed,
  onSelectMajor,
  onConfirmed,
  onRequestChange,
}: MajorConfirmPanelProps) {
  const [majors, setMajors] = useState<MajorListEntry[]>([]);
  const [pendingId, setPendingId] = useState(selectedMajorId ?? detection?.major_id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listMajors()
      .then((r) => setMajors(r.majors ?? []))
      .catch(() => setMajors([]));
  }, []);

  useEffect(() => {
    setPendingId(selectedMajorId ?? detection?.major_id ?? "");
  }, [selectedMajorId, detection?.major_id]);

  if (!detection && !selectedMajorId) return null;

  const displayName =
    majors.find((m) => m.major_id === (selectedMajorId ?? pendingId))?.name ??
    detection?.name ??
    selectedMajorId ??
    "";

  const handleConfirm = async () => {
    const mid = pendingId.trim();
    if (!mid) {
      setError("Please select a major.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const entry = majors.find((m) => m.major_id === mid);
      await confirmStudentMajor(userId, mid, "user");
      onSelectMajor(mid, entry?.name ?? mid);
      onConfirmed();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (majorConfirmed && selectedMajorId) {
    return (
      <div data-testid="major-confirmed-banner">
        <span className="font-medium">Current major:</span> {displayName} ({selectedMajorId})
        <button
          type="button"
          className="ml-2 text-neutral-600 underline hover:text-[var(--scu-text)]"
          onClick={() => onRequestChange?.()}
        >
          Change
        </button>
      </div>
    );
  }

  return (
    <div data-testid="major-confirm-panel">
      <p className="mb-2 font-medium">
        {detection?.message ??
          "Please confirm your major so we can apply the right degree requirements and prerequisites."}
      </p>
      {detection?.confidence && detection.major_id && (
        <p className="mb-2 text-neutral-600">
          Detected: {detection.name} ({detection.major_id})
          {detection.confidence === "low" ? " — low confidence" : ""}
        </p>
      )}
      <label className="mb-1 block text-xs font-medium text-neutral-700">Major</label>
      <select
        className="mb-2 w-full rounded border border-neutral-300 bg-white px-2 py-1.5 text-sm"
        value={pendingId}
        onChange={(e) => setPendingId(e.target.value)}
        data-testid="major-select"
      >
        <option value="">— Select major —</option>
        {majors.map((m) => (
          <option key={m.major_id} value={m.major_id}>
            {m.name} ({m.major_id})
          </option>
        ))}
      </select>
      {error && <p className="mb-2 text-red-700">{error}</p>}
      <button
        type="button"
        disabled={busy || !pendingId}
        className="rounded bg-[var(--scu-red)] px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
        onClick={() => void handleConfirm()}
        data-testid="major-confirm-btn"
      >
        {busy ? "Saving…" : "Confirm major"}
      </button>
      <p className="mt-2 text-xs text-neutral-500">
        Confirm your major before generating a schedule. Planning uses required courses and
        prerequisites from{" "}
        <code className="text-xs">data/majors/{pendingId || "…"}.md</code>.
      </p>
    </div>
  );
}
