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
      setError("请先选择专业。");
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
      <div
        className="mx-3 mt-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900"
        data-testid="major-confirmed-banner"
      >
        <span className="font-medium">当前专业：</span>
        {displayName} ({selectedMajorId})
        <button
          type="button"
          className="ml-2 text-emerald-700 underline hover:text-emerald-900"
          onClick={() => onRequestChange?.()}
        >
          更改
        </button>
      </div>
    );
  }

  return (
    <div
      className="mx-3 mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-950"
      data-testid="major-confirm-panel"
    >
      <p className="mb-2 font-medium">
        {detection?.message ??
          "请确认你的专业，以便我们按学位要求与先修课推荐课程。"}
      </p>
      {detection?.confidence && detection.major_id && (
        <p className="mb-2 text-amber-800">
          系统判断：{detection.name}（{detection.major_id}）
          {detection.confidence === "low" ? " — 置信度较低" : ""}
        </p>
      )}
      <label className="mb-1 block text-xs font-medium text-amber-900">专业</label>
      <select
        className="mb-2 w-full rounded border border-amber-300 bg-white px-2 py-1.5 text-sm"
        value={pendingId}
        onChange={(e) => setPendingId(e.target.value)}
        data-testid="major-select"
      >
        <option value="">— 选择专业 —</option>
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
        className="rounded bg-amber-800 px-3 py-1.5 text-white disabled:opacity-50"
        onClick={() => void handleConfirm()}
        data-testid="major-confirm-btn"
      >
        {busy ? "保存中…" : "确认专业"}
      </button>
      <p className="mt-2 text-xs text-amber-800">
        确认后才能生成课表；规划会使用 <code className="text-xs">data/majors/{pendingId || "…"}.md</code> 中的必修课与先修课。
      </p>
    </div>
  );
}
