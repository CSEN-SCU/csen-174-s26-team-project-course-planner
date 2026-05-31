import React from "react";
import { act, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearLocalSession,
  persistSessionToken,
  persistUserId,
  readStoredUserId,
} from "../../web/src/auth/session";
import { useAuth } from "../../web/src/hooks/useAuth";
import { Root } from "../../web/src/Root";

vi.mock("../../web/src/api/client", () => ({
  getMemory: vi.fn(async () => ({ memories: [] })),
  saveMemory: vi.fn(async () => ({ id: 1 })),
  deleteMemory: vi.fn(async () => {}),
  deleteAllUserData: vi.fn(async () => {}),
  generateFourYearPlan: vi.fn(async () => ({ plan: null })),
  listCourses: vi.fn(async () => []),
  googleSignInUrl: vi.fn(() => ""),
  listMajors: vi.fn(async () => ({ majors: [] })),
  confirmStudentMajor: vi.fn(async () => ({})),
}));

vi.mock("../../web/src/components/ChatPanel", () => ({
  ChatPanel: ({ onSignOut }: { onSignOut?: () => void }) => (
    <div data-testid="chat-panel">
      {onSignOut ? (
        <button type="button" onClick={onSignOut}>
          Sign out
        </button>
      ) : null}
    </div>
  ),
}));

vi.mock("../../web/src/components/CalendarView", () => ({
  CalendarView: () => <div data-testid="calendar-view" />,
}));

vi.mock("../../web/src/components/FourYearPlanView", () => ({
  FourYearPlanView: () => <div data-testid="four-year-view" />,
}));

vi.mock("../../web/src/components/SlotSuggestionPopover", () => ({
  SlotSuggestionPopover: () => null,
}));

vi.mock("../../web/src/components/AddCoursePicker", () => ({
  AddCoursePicker: () => null,
}));

vi.mock("../../web/src/components/SiteFooter", () => ({
  SiteFooter: () => null,
}));

vi.mock("../../web/src/components/GoogleSignInButton", () => ({
  GoogleSignInButton: () => <button type="button">Sign in with Google</button>,
}));

describe("sign out", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    sessionStorage.clear();
    window.history.replaceState({}, "", "/");
    localStorage.clear();
    document.documentElement.classList.remove("planner-shell");
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("clearLocalSession removes stored credentials", () => {
    persistUserId("user-123");
    persistSessionToken("token-abc");
    expect(readStoredUserId()).toBe("user-123");

    clearLocalSession();

    expect(readStoredUserId()).toBeNull();
    expect(sessionStorage.getItem("scu_planner_user_id_v2")).toBeNull();
    expect(sessionStorage.getItem("scu_planner_session_token")).toBeNull();
  });

  it("useAuth signOut clears session after a one second delay", () => {
    persistUserId("user-123");
    persistSessionToken("token-abc");

    const { result } = renderHook(() => useAuth());
    expect(result.current.userId).toBe("user-123");

    act(() => {
      result.current.signOut();
    });

    expect(result.current.signOutPending).toBe(true);
    expect(result.current.userId).toBe("user-123");
    expect(readStoredUserId()).toBe("user-123");

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.signOutPending).toBe(false);
    expect(result.current.userId).toBeNull();
    expect(readStoredUserId()).toBeNull();
  });

  it("clicking Sign out shows a loading screen then returns to home", () => {
    persistUserId("user-123");
    persistSessionToken("token-abc");
    localStorage.setItem("scu_planner_intro_seen:user-123", "true");
    document.documentElement.classList.add("planner-shell");

    render(<Root />);

    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();

    act(() => {
      screen.getByRole("button", { name: /^sign out$/i }).click();
    });

    expect(screen.queryByTestId("chat-panel")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/signing out/i);

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(screen.getByRole("button", { name: /sign in with google/i })).toBeInTheDocument();
    expect(readStoredUserId()).toBeNull();
    expect(document.documentElement.classList.contains("planner-shell")).toBe(false);
  });
});
