import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";

const PREFIX = "scrypt";

function parseStored(stored: string): { saltHex: string; hash: Buffer } | null {
  if (!stored.startsWith(`${PREFIX}$`)) return null;
  const parts = stored.split("$");
  if (parts.length !== 3) return null;
  const [, saltHex, hashHex] = parts;
  if (!saltHex || !hashHex || !/^[0-9a-f]+$/i.test(saltHex) || !/^[0-9a-f]+$/i.test(hashHex)) {
    return null;
  }
  try {
    return { saltHex, hash: Buffer.from(hashHex, "hex") };
  } catch {
    return null;
  }
}

export function hashPassword(password: string): string {
  const salt = randomBytes(16).toString("hex");
  const hash = scryptSync(password, salt, 64);
  return `${PREFIX}$${salt}$${hash.toString("hex")}`;
}

export function verifyPassword(password: string, stored: string): boolean {
  const parsed = parseStored(stored);
  if (!parsed) return false;
  const candidate = scryptSync(password, parsed.saltHex, parsed.hash.length);
  if (candidate.length !== parsed.hash.length) return false;
  return timingSafeEqual(candidate, parsed.hash);
}
