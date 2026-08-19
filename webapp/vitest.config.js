import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import AllureReporter from "allure-vitest/reporter";

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: "happy-dom",
    setupFiles: ["allure-vitest/setup", "./tests/setup.js"],
    reporters: ["verbose", new AllureReporter({ resultsDir: "../allure-results" })],
  },
});
