export function createSessionCookie(input: { studentKey: string }): {
  options: { secure?: boolean; httpOnly?: boolean; sameSite?: "lax" | "strict" | "none" };
} {
  void input;
  const secure = process.env.NODE_ENV === "production";
  return {
    options: {
      secure,
      httpOnly: true,
      sameSite: "lax"
    }
  };
}
