import { chromium, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { once } from "node:events";
import assert from "node:assert/strict";
import { checkRunningUI } from "../../tools/check-running-ui.mjs";

const root = resolve(".ui-test-data", `flow-${Date.now()}`);
const shots = resolve("test-results", "ui");
await mkdir(root, { recursive: true });
await mkdir(shots, { recursive: true });
const server = spawn(
  "python",
  ["-m", "server.http_server", "--data-dir", root, "--port", "0", "--no-browser"],
  { stdio: ["ignore", "pipe", "pipe"] },
);
const [out] = await once(server.stdout, "data");
const base = String(out).match(/http:\/\/[^ ]+/)[0];
let browser, page;
try {
  browser = await chromium.launch({
    channel: process.env.SYNOPSIS_BROWSER || "chrome",
    headless: true,
  });
  console.log(`Browser: ${browser.version()}`);
  page = await browser.newPage({
    viewport: { width: 1536, height: 1000 },
    deviceScaleFactor: 1,
  });
  page.setDefaultTimeout(10000);
  const errors = [];
  const external = [];
  page.on("pageerror", (e) => {
    errors.push(e.message);
    console.error("PAGE ERROR:", e.stack);
  });
  page.on("request", (r) => {
    if (/^https?:/.test(r.url()) && !r.url().startsWith(base))
      external.push(r.url());
  });
  await page.goto(base);
  await expect(
    page.getByRole("button", { name: "Новый курс", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Ваш первый курс", exact: false }),
  ).toBeVisible();
  await page.screenshot({
    path: resolve(shots, "01-home.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Новый курс", exact: true }).click();
  await page
    .getByLabel("Название курса", { exact: true })
    .fill("Линейная алгебра");
  await page.getByRole("button", { name: "Создать курс", exact: true }).click();
  await expect(page).toHaveURL(/\/courses\/[a-zA-Z0-9-]+$/);
  await expect(page.locator("#sidebar-course-title")).toHaveText(
    "Линейная алгебра",
  );
  const cid = page.url().split("/").at(-1);
  const delivery = await checkRunningUI(base);
  assert.equal(delivery.noteDialogChecked, true);
  await page.screenshot({
    path: resolve(shots, "02-workspace-empty.png"),
    fullPage: true,
  });
  console.log(`PASS visible home, course creation and navigation: ${cid}`);
  const snapshot = async () => {
    const response = await page.request.get(`${base}/api/courses/${cid}`);
    assert.equal(response.status(), 200);
    return response.json();
  };
  const dialog = () => page.locator("dialog[open]");
  async function createNote({
    kind = "concept",
    title,
    summary = "",
    markdown = "",
    lecture = null,
    card = true,
  }) {
    await page.locator("#new-note").click();
    await dialog()
      .getByLabel("Тип конспекта", { exact: true })
      .selectOption(kind);
    await dialog().getByLabel("Название", { exact: true }).fill(title);
    await dialog()
      .getByLabel("Краткое описание", { exact: true })
      .fill(summary);
    await dialog()
      .getByLabel("Текст конспекта · Markdown", { exact: true })
      .fill(markdown);
    if (lecture)
      await dialog()
        .getByLabel("Лекция определения", { exact: true })
        .selectOption(lecture);
    if (!card) await dialog().getByLabel("Создать карточку на карте").uncheck();
    await dialog()
      .getByRole("button", { name: "Создать конспект", exact: true })
      .click();
    await expect(dialog()).toHaveCount(0);
    await expect(page.locator(".note-heading h1")).toHaveText(title);
    return (await snapshot()).notes.find((n) => n.title === title);
  }
  async function selectText(text, { last = false } = {}) {
    await page.locator("#note-reader").evaluate(
      (reader, { text, last }) => {
        const span = [...reader.querySelectorAll("[data-source-span]")].find(
          (s) =>
            s.childNodes.length === 1 &&
            s.firstChild.nodeType === Node.TEXT_NODE &&
            s.textContent.includes(text),
        );
        if (!span) throw new Error("No rendered text: " + text);
        const start = last
          ? span.textContent.lastIndexOf(text)
          : span.textContent.indexOf(text);
        const range = document.createRange();
        range.setStart(span.firstChild, start);
        range.setEnd(span.firstChild, start + text.length);
        window.getSelection().removeAllRanges();
        window.getSelection().addRange(range);
        reader.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
      },
      { text, last },
    );
    await expect(page.locator("#selection-toolbar")).toBeVisible();
  }
  async function openNote(note) {
    await page.locator(`#notes-list [data-note-id="${note.id}"]`).click();
    await expect(page.locator(".note-heading h1")).toHaveText(note.title);
  }
  const lecture = await createNote({
    kind: "lecture",
    title: "Лекция 1. Векторные пространства",
    summary: "От геометрии к линейной алгебре",
    markdown:
      "## План занятия\n\n- Векторы и линейные комбинации\n- Базис и размерность",
  });
  assert.match(lecture.markdown, /План занятия/);
  assert.equal(lecture.summary, "От геометрии к линейной алгебре");
  const original =
    "# От геометрии к алгебре\n\nВектор — это элемент линейного пространства. **Сложение** и умножение на скаляр дают новые векторы.\n\nБазис позволяет однозначно записать координаты.\n\nНезависимость — важное свойство системы векторов.\n\nУчебник содержит доказательства.\n\n😀 повтор повтор.\n\n| Операция | Обозначение |\n|---|---|\n| Сложение | $u+v$ |\n| Масштаб | $\\lambda v$ |\n\n$$\n\\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}\\begin{pmatrix}x\\\\y\\end{pmatrix}=\\begin{pmatrix}x\\\\y\\end{pmatrix}\n$$\n\n- [x] Разобрать определение\n- [ ] Решить задачи";
  const vector = await createNote({
    title: "Вектор",
    summary: "Элемент пространства: направление, длина и координаты",
    markdown: original,
    lecture: lecture.id,
  });
  await expect(page.locator("#note-reader table td")).toHaveCount(4);
  await expect(page.locator("#note-reader .katex")).toHaveCount(3);
  await page.screenshot({
    path: resolve(shots, "03-reading.png"),
    fullPage: true,
  });
  assert.equal(vector.defined_in_lecture_note_id, lecture.id);
  let snap = await snapshot();
  assert.equal(
    snap.cards.find((c) => c.note_id === vector.id).lecture_box_id,
    snap.lecture_boxes[0].id,
  );
  console.log(
    "PASS lecture, assigned concept, real table and matrix rendering",
  );

  // CodeMirror drafts survive tab changes, refreshes and a failed HTTP save.
  await page.locator("[data-mode=edit]").click();
  const draft = original + "\n\nЧерновик с важной мыслью.";
  await page.locator(".cm-content").fill(draft);
  await openNote(lecture);
  await openNote(vector);
  await expect(page.locator(".cm-content")).toContainText(
    "Черновик с важной мыслью.",
  );
  const saveUrl = `${base}/api/courses/${cid}/notes/${vector.id}/save`;
  await page.route(
    saveUrl,
    (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: "Тестовая ошибка записи" }),
      }),
    { times: 1 },
  );
  await page.locator("#save-note").click();
  await expect(page.locator(".toast.error")).toContainText(
    "Тестовая ошибка записи",
  );
  assert.equal(
    (await snapshot()).notes.find((n) => n.id === vector.id).markdown,
    original,
  );
  await expect(page.locator(".cm-content")).toContainText(
    "Черновик с важной мыслью.",
  );
  await page.locator("#save-note").click();
  await expect(page.locator("#note-reader")).toContainText(
    "Черновик с важной мыслью.",
  );
  assert.equal(
    (await snapshot()).notes.find((n) => n.id === vector.id).markdown,
    draft,
  );
  console.log("PASS CodeMirror, draft tab retention, failed save and recovery");

  await selectText("Базис");
  await page.locator("[data-selection=create-note]").click();
  await dialog()
    .getByLabel("Лекция определения", { exact: true })
    .selectOption(lecture.id);
  await dialog()
    .getByLabel("Краткое описание", { exact: true })
    .fill("Независимая система, порождающая всё пространство");
  await dialog()
    .getByRole("button", { name: "Создать конспект", exact: true })
    .click();
  await expect(page.locator(".note-heading h1")).toHaveText("Базис");
  snap = await snapshot();
  const basis = snap.notes.find((n) => n.title === "Базис");
  assert.equal(basis.defined_in_lecture_note_id, lecture.id);
  assert.equal(snap.edges.length, 0);
  assert.ok(
    snap.notes
      .find((n) => n.id === vector.id)
      .markdown.includes(`[Базис](synopsis://note/${basis.id})`),
  );
  await openNote(vector);
  await selectText("повтор", { last: true });
  await page.locator("[data-selection=link]").click();
  await dialog().locator(`input[value="${basis.id}"]`).check();
  await dialog()
    .getByRole("button", { name: "Добавить ссылку", exact: true })
    .click();
  await expect(dialog()).toHaveCount(0);
  assert.ok(
    (await snapshot()).notes
      .find((n) => n.id === vector.id)
      .markdown.includes(`😀 повтор [повтор](synopsis://note/${basis.id}).`),
  );
  await selectText("Независимость");
  await page.locator("[data-selection=fact]").click();
  await dialog()
    .getByLabel("Текст факта · Markdown", { exact: true })
    .fill("Нулевая комбинация имеет только **нулевые** коэффициенты.");
  await dialog()
    .getByRole("button", { name: "Добавить факт", exact: true })
    .click();
  await expect(dialog()).toHaveCount(0);
  await page.locator("#note-reader .fact-link").click();
  await expect(dialog().locator("strong")).toHaveText("нулевые");
  await page.keyboard.press("Escape");
  console.log(
    "PASS exact UTF-16 selection, atomic new concept, note link and fact popover",
  );

  const pdfPage = await browser.newPage();
  await pdfPage.setContent(
    "<h1>Linear algebra</h1><p>Local PDF source for the browser test.</p>",
  );
  const pdf = await pdfPage.pdf();
  await pdfPage.close();
  await page.locator("[data-catalog=sources]").click();
  await page.locator("#source-input").setInputFiles({
    name: "Учебник.pdf",
    mimeType: "application/pdf",
    buffer: pdf,
  });
  await expect(page.locator("#sources-list")).toContainText("Учебник.pdf");
  await page.locator("[data-source-attach]").click();
  await dialog()
    .getByLabel("Начальная страница PDF", { exact: true })
    .fill("1");
  await dialog()
    .getByRole("button", { name: "Сохранить", exact: true })
    .click();
  await expect(dialog()).toHaveCount(0);
  await page.locator("[data-catalog=notes]").click();
  await selectText("Учебник");
  await page.locator("[data-selection=source]").click();
  await dialog().getByLabel("Страница PDF", { exact: true }).fill("1");
  await dialog()
    .getByRole("button", { name: "Добавить ссылку", exact: true })
    .click();
  await expect(dialog()).toHaveCount(0);
  snap = await snapshot();
  assert.equal(snap.sources.length, 1);
  assert.equal(snap.lecture_source_attachments.length, 1);
  const popupPromise = page.waitForEvent("popup");
  await page.locator("#note-reader .source-link").click();
  const popup = await popupPromise;
  await expect.poll(() => popup.url()).toContain("/assets/");
  await expect.poll(() => popup.url()).toContain("#page=1");
  await popup.close();
  await page.locator("[data-mode=edit]").click();
  const imageBuffer = await page.locator("#course-map").screenshot();
  await page.locator(".cm-content").press("Control+End");
  await page.locator(".cm-content").press("Enter");
  await page.locator("#image-input").setInputFiles({
    name: "Карта.png",
    mimeType: "image/png",
    buffer: imageBuffer,
  });
  await expect(page.locator(".cm-content")).toContainText("synopsis://asset/");
  await page.locator("#save-note").click();
  await expect(page.locator("#note-reader img")).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator("#note-reader img")
        .evaluate((img) => img.complete && img.naturalWidth > 0),
    )
    .toBe(true);
  console.log(
    "PASS local PDF upload, lecture attachment, page deep-link and image rendering",
  );

  const example = await createNote({
    kind: "example",
    title: "Плоскость R²",
    summary: "Две координаты — один вектор",
    markdown: "Вектор $(2,3)$ на плоскости.",
  });
  const task = await createNote({
    kind: "task",
    title: "Найти координаты",
    summary: "Разложить вектор по базису",
    markdown: "Решите систему $Ax=b$.",
  });
  await createNote({
    kind: "externalConcept",
    title: "Поле",
    summary: "Скаляры и допустимые операции",
    markdown: "Определение из курса алгебры.",
  });
  const cardless = await createNote({
    title: "Заметки к экзамену",
    markdown: "Этот конспект пока без карточки.",
    card: false,
  });
  await page.locator("#cardless-filter").check();
  await expect(page.locator("#notes-list .note-list-item")).toHaveCount(1);
  await page.locator("#cardless-filter").uncheck();
  await page.locator("#note-search").fill("координаты");
  await expect(page.locator("#notes-list .note-list-item")).toHaveCount(3);
  await page.locator("#note-search").fill("");
  snap = await snapshot();
  assert.equal(snap.edges.length, 0);
  const vectorCard = snap.cards.find((c) => c.note_id === vector.id),
    basisCard = snap.cards.find((c) => c.note_id === basis.id);
  await page.locator("#new-edge").click();
  await dialog()
    .getByLabel("Тип связи", { exact: true })
    .selectOption("hierarchical");
  await dialog()
    .getByLabel("Откуда", { exact: true })
    .selectOption(vectorCard.id);
  await dialog().getByLabel("Куда", { exact: true }).selectOption(basisCard.id);
  await dialog()
    .getByLabel("Подпись связи", { exact: true })
    .fill("задаёт координаты");
  await dialog()
    .getByRole("button", { name: "Создать связь", exact: true })
    .click();
  await expect(dialog()).toHaveCount(0);
  await page.locator("#zoom-fit").click();
  await expect(page.locator("[data-edge]")).toHaveCount(1);
  await page.locator("[data-edge] text").click();
  await page.locator("[data-edge-action=point]").click();
  await expect(page.locator("[data-control]")).toHaveCount(1);
  const originalControl = (await snapshot()).edges[0].geometry
    .control_points[0];
  const control = await page.locator("[data-control]").boundingBox();
  await page.mouse.move(
    control.x + control.width / 2,
    control.y + control.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(control.x + 55, control.y - 20, { steps: 6 });
  await page.mouse.up();
  await expect
    .poll(async () =>
      JSON.stringify((await snapshot()).edges[0].geometry.control_points[0]),
    )
    .not.toBe(JSON.stringify(originalControl));
  const before = await snapshot(),
    box = before.lecture_boxes[0],
    boxBounds = await page.locator(`[data-box="${box.id}"]`).boundingBox();
  const moved = page.waitForResponse((r) => r.url().endsWith("/map/move-box"));
  await page.mouse.move(boxBounds.x + 35, boxBounds.y + 15);
  await page.mouse.down();
  await page.mouse.move(boxBounds.x + 65, boxBounds.y + 50, { steps: 6 });
  await page.mouse.up();
  assert.equal((await moved).status(), 200);
  const after = await snapshot(),
    boxAfter = after.lecture_boxes[0],
    childBefore = before.cards.find((c) => c.id === vectorCard.id),
    childAfter = after.cards.find((c) => c.id === vectorCard.id);
  assert.ok(
    Math.abs(
      boxAfter.position.x -
        box.position.x -
        (childAfter.position.x - childBefore.position.x),
    ) < 1e-7,
  );
  assert.ok(
    Math.abs(
      boxAfter.position.y -
        box.position.y -
        (childAfter.position.y - childBefore.position.y),
    ) < 1e-7,
  );
  await page.locator("#map-settings").click();
  await dialog().locator("[name=visible-task]").uncheck();
  await dialog()
    .getByRole("button", { name: "Применить", exact: true })
    .click();
  await expect(dialog()).toHaveCount(0);
  await expect(page.locator(`[data-card][data-note="${task.id}"]`)).toHaveCount(
    0,
  );
  assert.ok(
    (await snapshot()).course.settings.map.hiddenNoteKinds.includes("task"),
  );
  await page.locator("#map-settings").click();
  await dialog().locator("[name=visible-task]").check();
  await dialog()
    .getByRole("button", { name: "Применить", exact: true })
    .click();
  await expect(dialog()).toHaveCount(0);
  await openNote(vector);
  await page.locator("#zoom-fit").click();
  await page.screenshot({
    path: resolve(shots, "04-workspace.png"),
    fullPage: true,
  });
  console.log(
    "PASS all note kinds, search, cardless filter, manual edge, control point, grouped dragging and settings",
  );

  // Removing a card leaves its note available; restoring makes exactly one card.
  await openNote(example);
  await page.locator("#note-menu").click();
  await dialog().locator("[data-note-action=remove-card]").click();
  await dialog()
    .getByRole("button", { name: "Убрать карточку", exact: true })
    .click();
  await expect(dialog()).toHaveCount(0);
  await expect
    .poll(async () =>
      (await snapshot()).cards.some((c) => c.note_id === example.id),
    )
    .toBe(false);
  await expect(page.locator("#note-reader")).toContainText("на плоскости");
  await page.locator("#locate-note").click();
  await expect
    .poll(
      async () =>
        (await snapshot()).cards.filter((c) => c.note_id === example.id).length,
    )
    .toBe(1);
  await page.reload();
  await expect(page.locator("#sidebar-course-title")).toHaveText(
    "Линейная алгебра",
  );
  await expect(page.locator(".note-heading h1")).toHaveText(example.title);
  assert.equal((await snapshot()).edges.length, 1);
  const downloadPromise = page.waitForEvent("download");
  await page.locator("#export-course").click();
  const download = await downloadPromise;
  const archivePath = resolve(root, "roundtrip.synopsis");
  await download.saveAs(archivePath);
  assert.equal(await download.failure(), null);
  // Same-library duplicate import must not overwrite the existing course.
  await page.goto(base);
  await page.locator("#import-input").setInputFiles(archivePath);
  await expect(page).toHaveURL(/\/courses\/[a-zA-Z0-9-]+$/);
  assert.notEqual(page.url().split("/").at(-1), cid);
  await expect(page.locator("#sidebar-course-title")).toHaveText(
    "Линейная алгебра",
  );
  const courses = await (await page.request.get(`${base}/api/courses`)).json();
  assert.equal(courses.length, 2);
  console.log(
    "PASS card restore, page reload, complete archive download and non-overwriting duplicate import",
  );
  // Import into a clean second library through the actual file input.
  const importRoot = resolve(root, "fresh-library");
  await mkdir(importRoot, { recursive: true });
  const importServer = spawn(
    "python",
    ["-m", "server.http_server", "--data-dir", importRoot, "--port", "0", "--no-browser"],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
  try {
    const [chunk] = await once(importServer.stdout, "data");
    const freshBase = String(chunk).match(/http:\/\/[^ ]+/)[0];
    await page.goto(freshBase);
    await page.locator("#import-input").setInputFiles(archivePath);
    await expect(page).toHaveURL(/\/courses\/[a-zA-Z0-9-]+$/);
    const importedId = page.url().split("/").at(-1);
    assert.notEqual(importedId, cid);
    await expect(page.locator("#sidebar-course-title")).toHaveText(
      "Линейная алгебра",
    );
    const restored = await (
      await page.request.get(`${freshBase}/api/courses/${importedId}`)
    ).json();
    const exported = await snapshot();
    for (const key of [
      "notes",
      "cards",
      "lecture_boxes",
      "edges",
      "facts",
      "sources",
      "assets",
      "lecture_source_attachments",
    ])
      assert.deepEqual(
        restored[key].map((row) => ({
          ...row,
          ...("course_id" in row ? { course_id: cid } : {}),
        })),
        exported[key],
        key + " round-trip",
      );
    await openNote(vector);
    await expect(page.locator("#note-reader img")).toBeVisible();
    await expect(page.locator("#note-reader .katex")).toHaveCount(3);
    await page.screenshot({
      path: resolve(shots, "05-imported.png"),
      fullPage: true,
    });
  } finally {
    importServer.kill();
    await once(importServer, "exit");
  }
  console.log(
    "PASS archive import into empty library, stable IDs/content/geometry/assets, rendered imported note",
  );
  assert.deepEqual(errors, [], "No browser JS errors");
  assert.deepEqual(
    external.filter((url) => !/^http:\/\/127\.0\.0\.1:\d+\//.test(url)),
    [],
    "All dependencies served locally",
  );
} catch (error) {
  await page
    ?.screenshot({ path: resolve(shots, "failure.png"), fullPage: true })
    .catch(() => {});
  throw error;
} finally {
  await browser?.close();
  server.kill();
  await once(server, "exit");
}
