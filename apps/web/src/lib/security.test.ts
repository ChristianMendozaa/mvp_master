import { describe, expect, it } from "vitest";

import { pkceChallenge, safeEqual, validateSameOrigin } from "./security";

describe("BFF security helpers", () => {
  it("uses the RFC 7636 S256 challenge", () => {
    expect(pkceChallenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")).toBe(
      "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    );
  });

  it("rejects cross-origin mutations", () => {
    expect(
      validateSameOrigin("http://localhost:3000", "http://localhost:3000"),
    ).toBe(true);
    expect(
      validateSameOrigin("https://attacker.test", "http://localhost:3000"),
    ).toBe(false);
  });

  it("compares state without accepting unequal lengths", () => {
    expect(safeEqual("same", "same")).toBe(true);
    expect(safeEqual("same", "different")).toBe(false);
  });
});
