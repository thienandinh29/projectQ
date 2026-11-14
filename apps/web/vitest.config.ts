import { configDefaults, defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  // Browser tests run with Playwright against a running stack (e2e/), not with Vitest.
  test: { exclude: [...configDefaults.exclude, "e2e/**"] },
});
