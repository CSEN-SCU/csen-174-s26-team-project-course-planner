import { useCallback, useState, type ReactNode } from "react";
import { deleteAllUserData } from "../api/client";
import { clearLocalSession } from "../auth/session";
import { DeleteUserDataConfirm } from "../components/DeleteUserDataConfirm";

export function useDeleteUserDataModal(userId: string | null) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const openDeleteModal = useCallback(() => {
    setNotice(null);
    setOpen(true);
  }, []);

  const cancelDelete = useCallback(() => {
    if (busy) return;
    setOpen(false);
    setNotice(null);
  }, [busy]);

  const confirmDelete = useCallback(async () => {
    if (!userId) return;
    setBusy(true);
    setNotice(null);
    let serverNotice: string | null = null;
    try {
      await deleteAllUserData(userId);
    } catch (e) {
      const hint = e instanceof Error ? e.message : "Could not reach the server.";
      serverNotice =
        "Signed out on this device. Server data could not be cleared (" +
        hint +
        ") — upload Academic Progress again after your next sign-in.";
    }
    clearLocalSession();
    setOpen(false);
    setBusy(false);
    setNotice(null);
    if (serverNotice) {
      try {
        sessionStorage.setItem("scu_delete_user_data_notice", serverNotice);
      } catch {
        /* ignore */
      }
    }
    window.location.href = "/";
  }, [userId]);

  const modal: ReactNode = (
    <DeleteUserDataConfirm
      open={open}
      busy={busy}
      error={notice}
      onConfirm={() => void confirmDelete()}
      onCancel={cancelDelete}
    />
  );

  return { openDeleteModal, deleteModal: modal };
}
