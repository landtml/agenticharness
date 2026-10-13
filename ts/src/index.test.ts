import { test } from "node:test";
import assert from "node:assert/strict";
import { HARNESS_VERSION } from "./index.js";

test("harness version is set", () => {
  assert.match(HARNESS_VERSION, /^\d+\.\d+\.\d+$/);
});
