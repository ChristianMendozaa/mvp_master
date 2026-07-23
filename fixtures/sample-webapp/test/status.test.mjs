import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("status card reports a delivered result", async () => {
  const document = JSON.parse(await readFile(new URL("../src/status.json", import.meta.url)));
  assert.equal(document.status, "Delivered by deterministic local agent");
});
