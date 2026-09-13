import { test } from "node:test";
import assert from "node:assert/strict";
import { chromium, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { once } from "node:events";

test("browser recovery: in-flight edits, reload, revision conflict, narrow layout and module failure", async () => {
  const root = resolve(".ui-test-data", `recovery-${Date.now()}`);
  await mkdir(root, { recursive: true });
  await mkdir("test-results/ui", { recursive: true });
  const server = spawn(
    "python",
    ["-m", "server.http_server", "--data-dir", root, "--port", "0", "--no-browser"],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
  const [chunk] = await once(server.stdout, "data");
  const base = String(chunk).match(/http:\/\/[^ ]+/)[0];
  let browser, page;
  try {
    browser = await chromium.launch({
      channel: process.env.SYNOPSIS_BROWSER || "chrome",
      headless: true,
    });
    page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.on("dialog", (dialog) => dialog.accept());
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.stack));
    const post = async (path, data) => {
      const r = await page.request.post(base + path, { data });
      assert.ok(r.ok(), await r.text());
      return r.json();
    };
    const course = await post("/api/courses", { title: "Проверка сохранения" });
    const api = `/api/courses/${course.id}`;
    const note = await post(api + "/notes", {
      title: "Надёжный черновик",
      markdown: "Исходная версия",
      with_card: true,
    });
    const stored = async () =>
      (await (await page.request.get(base + api)).json()).notes.find(
        (n) => n.id === note.id,
      );
    await page.goto(`${base}/courses/${course.id}`);
    await page.locator(`[data-note-id="${note.id}"]`).click();
    await page.locator("[data-mode=edit]").click();
    await page.locator(".cm-content").fill("Отправленная версия");
    let heldRoute, notifyHeld;
    const held = new Promise((resolve) => {
      notifyHeld = resolve;
    });
    await page.route(
      base + api + `/notes/${note.id}/save`,
      async (route) => {
        heldRoute = route;
        notifyHeld();
      },
      { times: 1 },
    );
    await page.locator("#save-note").click();
    await held;
    await page.locator(".cm-content").fill("Отправленная версия + новая мысль");
    await heldRoute.continue();
    await expect
      .poll(async () => (await stored()).markdown)
      .toBe("Отправленная версия");
    await expect(page.locator("#save-state")).toContainText(
      "Есть несохранённый черновик",
    );
    await expect(page.locator(".cm-content")).toContainText("+ новая мысль");
    await page.locator("#save-note").click();
    await expect(page.locator("#note-reader")).toContainText("+ новая мысль");

    await page.locator("[data-mode=edit]").click();
    await page.locator(".cm-content").fill("Черновик переживает перезагрузку");
    await page.reload();
    await expect(page.locator(".cm-content")).toContainText(
      "Черновик переживает перезагрузку",
    );
    assert.equal(
      (await stored()).markdown,
      "Отправленная версия + новая мысль",
    );
    let saved = await stored();
    await post(api + `/notes/${note.id}/save`, {
      markdown: "Изменено в другой вкладке",
      revision: saved.revision,
    });
    await page.locator("#save-note").click();
    const conflict = page.getByRole("dialog", {
      name: "Сохранённая версия изменилась",
    });
    await expect(conflict).toBeVisible();
    await expect(
      conflict.getByLabel("Сохранено в курсе", { exact: true }),
    ).toHaveValue("Изменено в другой вкладке");
    await expect(
      conflict.getByLabel("Ваш локальный черновик", { exact: true }),
    ).toHaveValue("Черновик переживает перезагрузку");
    await page.screenshot({
      path: "test-results/ui/06-conflict.png",
      fullPage: true,
    });
    await conflict
      .getByRole("button", { name: "Оставить мой черновик", exact: true })
      .click();
    await expect(conflict).toHaveCount(0);
    assert.equal(
      (await stored()).markdown,
      "Изменено в другой вкладке",
      "Rebase must not automatically overwrite storage",
    );
    await expect(page.locator(".cm-content")).toContainText(
      "Черновик переживает перезагрузку",
    );
    await page.locator("#save-note").click();
    await expect(page.locator("#note-reader")).toContainText(
      "Черновик переживает перезагрузку",
    );
    assert.equal((await stored()).markdown, "Черновик переживает перезагрузку");

    await page.locator("[data-mode=edit]").click();
    await page.locator(".cm-content").fill("Этот черновик будет явно заменён");
    saved = await stored();
    await post(api + `/notes/${note.id}/save`, {
      markdown: "Актуальная сохранённая версия",
      revision: saved.revision,
    });
    await page.locator("#save-note").click();
    await expect(conflict).toBeVisible();
    await conflict
      .getByRole("button", {
        name: "Загрузить сохранённую версию",
        exact: true,
      })
      .click();
    await expect(conflict).toHaveCount(0);
    await expect(page.locator("#note-reader")).toContainText(
      "Актуальная сохранённая версия",
    );

    await page.locator("#panel-splitter").focus();
    const oldWidth = Number(
      await page.locator("#panel-splitter").getAttribute("aria-valuenow"),
    );
    await page.locator("#panel-splitter").press("ArrowRight");
    await expect(page.locator("#panel-splitter")).toHaveAttribute(
      "aria-valuenow",
      String(oldWidth + 3),
    );
    await page.setViewportSize({ width: 800, height: 1000 });
    await page.locator("#zoom-fit").click();
    await page.screenshot({
      path: "test-results/ui/07-narrow.png",
      fullPage: true,
    });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
      "No horizontal document overflow",
    );
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator("#zoom-fit").click();
    await page.screenshot({
      path: "test-results/ui/09-mobile.png",
      fullPage: true,
      animations: "disabled",
    });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
      "No horizontal mobile overflow",
    );
    assert.deepEqual(errors, []);

    // A missing ESM resource must produce a recovery message, not a blank shell.
    const broken = await browser.newPage();
    await broken.route("**/static/home.js", (route) => route.abort());
    await broken.goto(base);
    await expect(broken.locator("#home-error")).toBeVisible({ timeout: 15000 });
    await expect(
      broken.getByRole("button", {
        name: "Перезагрузить страницу",
        exact: true,
      }),
    ).toBeVisible();
    await broken.screenshot({
      path: "test-results/ui/08-load-error.png",
      fullPage: true,
    });
    await broken.close();
    const missingCourse = await browser.newPage();
    await missingCourse.route("**/static/course.js", (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: "Файл интерфейса не найден" }),
      }),
    );
    await missingCourse.goto(`${base}/courses/${course.id}`);
    await expect(missingCourse.locator("#course-error")).toContainText(
      "/static/course.js",
    );
    await expect(missingCourse.locator("#new-note")).toBeDisabled();
    await expect(
      missingCourse.getByRole("link", { name: "Диагностика сервера" }),
    ).toHaveAttribute("href", "/api/health");
    await missingCourse.screenshot({
      path: "test-results/ui/10-missing-course-script.png",
      fullPage: true,
    });
    await missingCourse.close();
  } catch (error) {
    await page
      ?.screenshot({
        path: "test-results/ui/recovery-failure.png",
        fullPage: true,
      })
      .catch(() => {});
    throw error;
  } finally {
    await browser?.close();
    server.kill();
    await once(server, "exit");
  }
});
