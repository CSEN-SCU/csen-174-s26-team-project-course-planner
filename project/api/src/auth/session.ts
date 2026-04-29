import crypto from "node:crypto";

export function createSessionCookie(input: { studentKey: string }) {
  const sessionId = crypto.randomUUID();

  return {
    name: "scu_session",
    value: `${input.studentKey}.${sessionId}`,
    options: {
      httpOnly: true,
      sameSite: "lax" as const,
      secure: process.env.NODE_ENV === "production",
      expires: new Date(Date.now() + 1000 * 60 * 60 * 24 * 7)
    }
  };
}

