import crypto from "node:crypto";

const SCRYPT_KEYLEN = 32;

export function hashPassword(password: string) {
  const salt = crypto.randomBytes(16).toString("hex");
  const key = crypto.scryptSync(password, salt, SCRYPT_KEYLEN).toString("hex");
  return `scrypt$${salt}$${key}`;
}

export function verifyPassword(password: string, stored: string) {
  const [scheme, salt, expectedKey] = stored.split("$");
  if (scheme !== "scrypt" || !salt || !expectedKey) return false;
  const key = crypto.scryptSync(password, salt, SCRYPT_KEYLEN);
  const expected = Buffer.from(expectedKey, "hex");
  if (expected.length !== key.length) return false;
  return crypto.timingSafeEqual(expected, key);
}

