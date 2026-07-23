import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

export function randomUrlToken(bytes = 32): string {
  return randomBytes(bytes).toString("base64url");
}

export function pkceChallenge(verifier: string): string {
  return createHash("sha256").update(verifier).digest("base64url");
}

export function safeEqual(first: string, second: string): boolean {
  const left = Buffer.from(first);
  const right = Buffer.from(second);
  return left.length === right.length && timingSafeEqual(left, right);
}

export function validateSameOrigin(
  origin: string | null,
  appUrl: string,
): boolean {
  if (!origin) return false;
  try {
    return new URL(origin).origin === new URL(appUrl).origin;
  } catch {
    return false;
  }
}
