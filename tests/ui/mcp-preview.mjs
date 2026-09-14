// Optional visual check of a course produced by the real MCP transport test.
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir } from "node:fs/promises";
import { chromium, expect } from "@playwright/test";
import assert from "node:assert/strict";

const [python, library, courseId, conceptId] = process.argv.slice(2);
const server = spawn(
  python,
  [
    "-m",
    "server.http_server",
    "--data-dir",
    library,
    "--port",
    "0",
    "--no-browser",
  ],
  { stdio: ["ignore", "pipe", "pipe"] },
);
let browser;
try {
  const url = await new Promise((resolve, reject) => {
    let output = "";
    const timer = setTimeout(
      () => reject(new Error("Server did not start: " + output)),
      10000,
    );
    server.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    server.once("exit", () => {
      clearTimeout(timer);
      reject(new Error("Server exited: " + output));
    });
    server.stdout.on("data", (chunk) => {
      output += chunk;
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) {
        clearTimeout(timer);
        resolve(match[0]);
      }
    });
    server.stderr.on("data", (chunk) => {
      output += chunk;
    });
  });
  browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage({
    viewport: { width: 1536, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`${url}/courses/${courseId}`);
  await expect(page.locator("#sidebar-course-title")).toHaveText("Тест MCP");
  await expect(page.locator(".map-box")).toHaveCount(1);
  await expect(page.locator(".map-card")).toHaveCount(2);
  await page.locator(`#notes-list [data-note-id="${conceptId}"]`).click();
  await expect(page.locator("#note-reader .katex")).toHaveCount(1);
  await expect(page.locator("#note-reader")).toContainText("Исходные слайды");
  await page.getByRole("link", { name: "Пояснение", exact: true }).click();
  await expect(page.locator("body")).toContainText(
    "Координаты зависят от базиса.",
  );
  await page.keyboard.press("Escape");
  await page.locator("[data-catalog=sources]").click();
  await expect(page.locator("#sources-list")).toContainText("slides.pdf");
  await mkdir("test-results/mcp", { recursive: true });
  await page.screenshot({
    path: "test-results/mcp/imported-course.png",
    fullPage: true,
  });
  assert.deepEqual(errors, []);
  console.log(
    "PASS MCP-generated archive in Chrome: frame/cards, formula, fact popover, PDF source; no page errors",
  );
} finally {
  await browser?.close();
  server.kill();
  if (server.exitCode === null) await once(server, "exit");
}
