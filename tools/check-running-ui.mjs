// Read-only verification of the user's actual running instance, not a new fixture server.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium, expect } from "@playwright/test";

export async function checkRunningUI(address = "http://localhost:8765") {
  const base = new URL(address);
  if (
    base.protocol !== "http:" ||
    !["localhost", "127.0.0.1"].includes(base.hostname) ||
    base.username ||
    base.password
  )
    throw new Error(
      "Проверка разрешена только для локального HTTP-сервера Synopsis.",
    );
  const get = async (path) => {
    const response = await fetch(new URL(path, base), {
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok)
      throw new Error(
        `${path}: HTTP ${response.status} — ${(await response.text()).slice(0, 500)}`,
      );
    return response;
  };
  const health = await (await get("/api/health")).json();
  assert.equal(health.app, "synopsis", "Это не текущий сервер Synopsis");
  assert.equal(
    health.ui.ok,
    true,
    `Отсутствуют: ${health.ui.missing_files.join(", ")}`,
  );
  console.log(
    `Instance: ${health.instance_id}\nUI directory: ${health.ui.root}\nData directory: ${health.data_dir}`,
  );
  for (const [name, info] of Object.entries(health.ui.files)) {
    assert.ok(
      /^[a-zA-Z0-9_./-]+$/.test(name) &&
        !name.startsWith("/") &&
        !name.split("/").includes(".."),
      "Недопустимый путь в диагностике сервера",
    );
    const response = await get("/static/" + name);
    assert.equal(
      response.headers.get("x-synopsis-instance"),
      health.instance_id,
      "Ответил другой процесс сервера",
    );
    if (name.endsWith(".js"))
      assert.match(
        response.headers.get("content-type"),
        /^(text|application)\/javascript/,
      );
    const bytes = Buffer.from(await response.arrayBuffer());
    assert.equal(
      createHash("sha256").update(bytes).digest("hex"),
      info.sha256,
      `${name}: сервер сообщил другую контрольную сумму`,
    );
    const local = await readFile(
      new URL("../frontend/" + name, import.meta.url),
    );
    assert.equal(
      createHash("sha256").update(bytes).digest("hex"),
      createHash("sha256").update(local).digest("hex"),
      `${name}: сервер отдаёт не текущий файл этого проекта`,
    );
  }
  console.log(
    `PASS delivered ${Object.keys(health.ui.files).length} UI files, exact local bytes and JS MIME types`,
  );
  let browser;
  try {
    browser = await chromium.launch({
      channel: process.env.SYNOPSIS_BROWSER || "chrome",
      headless: true,
    });
    const page = await browser.newPage();
    // The checker must not create or modify any user course, even accidentally.
    await page.route("**/api/**", (route) =>
      route.request().method() === "GET" ? route.continue() : route.abort(),
    );
    const errors = [],
      failures = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("response", (response) => {
      if (!response.ok())
        failures.push(`${response.status()} ${response.url()}`);
    });
    page.on("requestfailed", (request) => failures.push(request.url()));
    await page.goto(base.origin);
    await expect(page.locator("#create-course")).toBeEnabled();
    const courses = await (await get("/api/courses")).json();
    if (courses.length) {
      await page.goto(
        new URL("/courses/" + encodeURIComponent(courses[0].id), base).href,
      );
      await expect(page.locator("#new-note")).toBeEnabled();
      await page.locator("#new-note").click();
      await expect(
        page.getByRole("dialog", { name: "Новый конспект", exact: true }),
      ).toBeVisible();
      await expect(page.getByLabel("Название", { exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Отмена", exact: true }).click();
      console.log(
        "PASS current instance: workspace loads and New note dialog opens. No POST requests or data writes.",
      );
    } else {
      console.log(
        "SKIP note dialog: the actual library has no courses. No test courses were created.",
      );
    }
    assert.deepEqual(errors, [], "JavaScript errors in the actual instance");
    assert.deepEqual(
      failures,
      [],
      "Failed browser requests in the actual instance",
    );
    return {
      instanceId: health.instance_id,
      files: Object.keys(health.ui.files).length,
      noteDialogChecked: courses.length > 0,
    };
  } finally {
    await browser?.close();
  }
}

if (
  process.argv[1] &&
  pathToFileURL(resolve(process.argv[1])).href === import.meta.url
) {
  const flag = process.argv.indexOf("--url");
  const address = flag < 0 ? "http://localhost:8765" : process.argv[flag + 1];
  try {
    await checkRunningUI(address);
  } catch (error) {
    const reason = error.cause?.code === "ECONNREFUSED"
      ? "соединение отклонено; сервер на этом адресе недоступен"
      : error.message;
    console.error(`FAIL ${address}: ${reason}`);
    process.exitCode = 1;
  }
}
