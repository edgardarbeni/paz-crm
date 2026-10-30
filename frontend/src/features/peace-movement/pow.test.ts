import { describe, expect, it } from "vitest";
import { solveChallenge } from "./pow";

async function sha256Hex(text: string) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

describe("solveChallenge", () => {
  it("finds the number the server hashed", async () => {
    const salt = "abc?issued=1&expires=2&";
    const challenge = await sha256Hex(`${salt}1234`);
    const number = await solveChallenge(
      { algorithm: "SHA-256", challenge, salt, signature: "x", max_number: 5000 },
      { batch: 250 },
    );
    expect(number).toBe(1234);
  });

  it("fails when the number is out of range", async () => {
    const salt = "s?";
    const challenge = await sha256Hex(`${salt}9999`);
    await expect(
      solveChallenge({ algorithm: "SHA-256", challenge, salt, signature: "x", max_number: 100 }),
    ).rejects.toThrow("verificación");
  });
});
