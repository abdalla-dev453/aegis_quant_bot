/**
 * scripts/error-coverage.mjs
 * Checks that every error code raised in the Python source appears in at
 * least one test file.  Prints untested codes and exits 1 if any are missing.
 *
 * Usage:  node scripts/error-coverage.mjs
 */

import fs from "fs";
import path from "path";

const ROOT = process.cwd();

// ── Source files that raise APIError ────────────────────────────────────────
const SOURCE_FILES = [
  path.join(ROOT, "lib", "ea-bridge", "app", "errors.py"),
  path.join(ROOT, "lib", "ea-bridge", "app", "security.py"),
  path.join(ROOT, "lib", "ea-bridge", "app", "routes", "app.py"),
  path.join(ROOT, "lib", "ea-bridge", "app", "routes", "ea.py"),
];

// ── Test files to check for coverage ────────────────────────────────────────
const TEST_FILES = [
  path.join(ROOT, "lib", "ea-bridge", "tests", "test_contracts.py"),
  path.join(ROOT, "lib", "ea-bridge", "tests", "test_integration.py"),
  path.join(ROOT, "lib", "ea-bridge", "tests", "test_integration_full.py"),
  path.join(ROOT, "lib", "ea-bridge", "tests", "test_security.py"),
  path.join(ROOT, "lib", "ea-bridge", "tests", "test_verification_int.py"),
  path.join(ROOT, "lib", "ea-bridge", "tests", "test_enhancements.py"),
];

// ── Extract error codes from source files ───────────────────────────────────
// Matches: APIError("some_code", ...) or raise APIError("some_code", ...)
const ERROR_CODE_RE = /APIError\(\s*["']([a-z_]+)["']/g;

const allCodes = new Set();
for (const src of SOURCE_FILES.filter(fs.existsSync)) {
  const text = fs.readFileSync(src, "utf8");
  let m;
  ERROR_CODE_RE.lastIndex = 0;
  while ((m = ERROR_CODE_RE.exec(text)) !== null) {
    allCodes.add(m[1]);
  }
}

if (allCodes.size === 0) {
  console.error("❌  No APIError codes found in source files. Check SOURCE_FILES list.");
  process.exit(1);
}

// ── Load test text ──────────────────────────────────────────────────────────
const testText = TEST_FILES.filter(fs.existsSync)
  .map((f) => fs.readFileSync(f, "utf8"))
  .join("\n");

// ── Compare ─────────────────────────────────────────────────────────────────
const missing = [];
const covered = [];

for (const code of [...allCodes].sort()) {
  // Look for the code string in any quote style used in assertions
  const found =
    testText.includes(`"${code}"`) ||
    testText.includes(`'${code}'`) ||
    testText.includes(`"code"] == "${code}"`) ||
    testText.includes(`"code"] in (`);

  if (found) {
    covered.push(code);
  } else {
    missing.push(code);
  }
}

console.log(`\nError code coverage: ${covered.length}/${allCodes.size} codes tested`);

if (covered.length > 0) {
  console.log("\n  Covered:");
  for (const c of covered) {
    console.log(`    ✅  ${c}`);
  }
}

if (missing.length > 0) {
  console.log("\n  Missing (no test references):");
  for (const c of missing) {
    console.log(`    ❌  ${c}`);
  }
  process.exit(1);
}

console.log(`\n✅  All ${allCodes.size} error codes have test references.`);
