/**
 * scripts/route-coverage.mjs
 * Compares routes registered in the FastAPI app against test files.
 * Prints untested routes and exits 1 if any are missing.
 *
 * Usage:  node scripts/route-coverage.mjs
 */

import fs from "fs";
import path from "path";

const ROOT = process.cwd();

// ── Sources of truth ────────────────────────────────────────────────────────
// 1. OpenAPI spec generated from the FastAPI app (preferred)
// 2. Fallback: parse route decorators from the Python source files
const OPENAPI_PATHS = [
  path.join(ROOT, "lib", "ea-contracts", "openapi.json"),
  path.join(ROOT, "lib", "api-spec", "openapi.yaml"),
];

// Route source files (fallback when no OpenAPI spec exists)
const ROUTE_SOURCES = [
  path.join(ROOT, "lib", "ea-bridge", "app", "routes", "app.py"),
  path.join(ROOT, "lib", "ea-bridge", "app", "routes", "ea.py"),
];

// Test files to search for coverage
const TEST_FILES = [
  path.join(ROOT, "lib", "ea-bridge", "tests", "test_contracts.py"),
  path.join(ROOT, "lib", "ea-bridge", "tests", "test_integration.py"),
  path.join(ROOT, "lib", "ea-bridge", "tests", "test_integration_full.py"),
  path.join(ROOT, "lib", "ea-bridge", "tests", "test_security.py"),
  path.join(ROOT, "lib", "ea-bridge", "tests", "test_verification_int.py"),
  path.join(ROOT, "lib", "ea-bridge", "tests", "test_enhancements.py"),
];

// ── Load test text ──────────────────────────────────────────────────────────
const testText = TEST_FILES.filter(fs.existsSync)
  .map((f) => fs.readFileSync(f, "utf8"))
  .join("\n");

// ── Helper: check if a route is referenced in tests ─────────────────────────
function isCovered(routePath) {
  // Strip path parameters {param} for fuzzy matching
  const base = routePath.replace(/\{[^}]+\}/g, "");
  const withoutLeadingSlash = base.replace(/^\//, "");
  return (
    testText.includes(routePath) ||
    testText.includes(base) ||
    testText.includes(withoutLeadingSlash)
  );
}

// ── Strategy 1: OpenAPI JSON spec ───────────────────────────────────────────
function loadFromOpenApi() {
  const specFile = OPENAPI_PATHS.find(fs.existsSync);
  if (!specFile) return null;

  const raw = fs.readFileSync(specFile, "utf8");
  const openapi = JSON.parse(raw);
  const routes = [];
  for (const [p, methods] of Object.entries(openapi.paths || {})) {
    for (const [method, op] of Object.entries(methods)) {
      if (["get", "post", "put", "patch", "delete"].includes(method)) {
        routes.push({
          method: method.toUpperCase(),
          path: p,
          summary: op.summary || op.operationId || p,
        });
      }
    }
  }
  return routes;
}

// ── Strategy 2: Parse FastAPI route decorators from Python source ────────────
function loadFromPythonSources() {
  const routes = [];
  const routeRe = /@router\.(get|post|put|patch|delete)\(\s*["']([^"']+)["']/g;

  for (const src of ROUTE_SOURCES.filter(fs.existsSync)) {
    const text = fs.readFileSync(src, "utf8");
    let m;
    routeRe.lastIndex = 0;
    while ((m = routeRe.exec(text)) !== null) {
      const method = m[1].toUpperCase();
      let routePath = m[2];
      // Prepend known prefix based on router prefix
      if (src.endsWith("app.py") && !routePath.startsWith("/app")) {
        routePath = "/app/v1" + routePath;
      } else if (src.endsWith("ea.py") && !routePath.startsWith("/ea")) {
        routePath = "/ea/v1" + routePath;
      }
      routes.push({ method, path: routePath, summary: routePath });
    }
  }
  return routes;
}

// ── Main ─────────────────────────────────────────────────────────────────────
const routes = loadFromOpenApi() ?? loadFromPythonSources();

if (routes.length === 0) {
  console.error("❌  Could not find any routes to check. Add an openapi.json or route source files.");
  process.exit(1);
}

const missing = routes.filter(({ path: p }) => !isCovered(p));

if (missing.length > 0) {
  console.log(`\nRoutes with no test coverage (${missing.length} of ${routes.length}):`);
  for (const r of missing) {
    console.log(`  ${r.method.padEnd(6)} ${r.path}  (${r.summary})`);
  }
  process.exit(1);
}

console.log(`✅  All ${routes.length} API routes have test references.`);
