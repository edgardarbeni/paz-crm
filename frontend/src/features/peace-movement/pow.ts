/** Proof of work of the public enrollment (D-86, ALTCHA-style): find `number` such that
 * SHA-256(salt + number) equals the challenge. It takes the browser a moment; it costs a bot
 * farm real work. Runs in small batches so the page stays responsive. */

export interface PowChallenge {
  algorithm: string;
  challenge: string;
  salt: string;
  signature: string;
  max_number: number;
}

const encoder = new TextEncoder();

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(text));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function solveChallenge(
  challenge: PowChallenge,
  { batch = 500, signal }: { batch?: number; signal?: AbortSignal } = {},
): Promise<number> {
  for (let start = 0; start <= challenge.max_number; start += batch) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const end = Math.min(start + batch, challenge.max_number + 1);
    const hashes = await Promise.all(
      Array.from({ length: end - start }, (_, i) => sha256Hex(`${challenge.salt}${start + i}`)),
    );
    const found = hashes.indexOf(challenge.challenge);
    if (found >= 0) return start + found;
    await new Promise((resolve) => setTimeout(resolve, 0)); // yield to the UI
  }
  throw new Error("No se pudo resolver la verificación.");
}
