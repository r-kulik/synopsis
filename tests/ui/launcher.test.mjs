import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { once } from "node:events";
import { chromium, expect } from "@playwright/test";

test("auto-open URL points to a ready app; create course and note via the launched UI", async () => {
  const data = resolve(".ui-test-data", `auto-open-${Date.now()}`);
  await mkdir(data, { recursive: true });
  const process = spawn(
    "python",
    [
      "-S",
      "-B",
      "tests/ui/launch-with-browser-probe.py",
      "--data-dir",
      data,
      "--port",
      "0",
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
  let browser;
  try {
    const url = await new Promise((resolve, reject) => {
      let output = "",
        errors = "";
      const timer = setTimeout(
        () => reject(new Error("No browser-open request: " + output + errors)),
        12000,
      );
      process.stderr.on("data", (chunk) => {
        errors += chunk;
      });
      process.once("exit", () => {
        clearTimeout(timer);
        reject(new Error("Launcher exited: " + output + errors));
      });
      process.stdout.on("data", (chunk) => {
        output += chunk;
        const match = output.match(/BROWSER_OPEN (http:\/\/127\.0\.0\.1:\d+)/);
        if (match) {
          clearTimeout(timer);
          resolve(match[1]);
        }
      });
    });
    const health = await (await fetch(url + "/api/health")).json();
    assert.equal(health.status, "ok");
    assert.equal(health.data_dir, data);
    browser = await chromium.launch({ channel: "chrome", headless: true });
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(url);
    await page.getByRole("button", { name: "Новый курс", exact: true }).click();
    await page
      .getByLabel("Название курса", { exact: true })
      .fill("Автоматический запуск");
    await page
      .getByRole("button", { name: "Создать курс", exact: true })
      .click();
    await page.locator("#new-note").click();
    await page.getByLabel("Название", { exact: true }).fill("Первый конспект");
    await page
      .getByLabel("Текст конспекта · Markdown", { exact: true })
      .fill("Приложение готово к работе.");
    await page
      .getByRole("dialog", { name: "Новый конспект", exact: true })
      .getByRole("button", { name: "Создать конспект", exact: true })
      .click();
    await expect(page.locator("#note-reader")).toContainText(
      "Приложение готово к работе.",
    );
    assert.deepEqual(errors, []);
  } finally {
    await browser?.close();
    process.kill();
    if (process.exitCode === null) await once(process, "exit");
  }
});
