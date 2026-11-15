// Playwright — E2E do Discovery Engine (/connect), contra backend/tests/connect_e2e_server.py (porta 8011).
const { defineConfig } = require("playwright/test");

module.exports = defineConfig({
  testDir: "./e2e",
  testMatch: /connect\.spec\.js/,
  workers: 1,
  timeout: 60000,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8011",
    channel: process.env.PW_CHANNEL || "chrome",
    headless: true,
    locale: "pt-PT",
    trace: "off",
  },
});
