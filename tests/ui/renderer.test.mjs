import { test } from "node:test";
import assert from "node:assert/strict";
import { chromium } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { once } from "node:events";

test("local Chrome: real Markdown, math, safe links and UTF-16 selection", async () => {
  const root = resolve(".ui-test-data", `renderer-${Date.now()}`);
  await mkdir(root, { recursive: true });
  const server = spawn(
    "python",
    ["-m", "server.http_server", "--data-dir", root, "--port", "0", "--no-browser"],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
  const [chunk] = await once(server.stdout, "data");
  const base = String(chunk).match(/http:\/\/[^ ]+/)[0];
  let browser;
  try {
    browser = await chromium.launch({ channel: "chrome", headless: true });
    const page = await browser.newPage({
      viewport: { width: 1536, height: 1000 },
    });
    await page.goto(base);
    await page
      .getByRole("button", { name: "Ваш первый курс", exact: false })
      .waitFor();
    await mkdir("test-results/ui", { recursive: true });
    await page.screenshot({
      path: "test-results/ui/01-home.png",
      fullPage: true,
    });
    const checks = await page.evaluate(async () => {
      const m = await import("/static/markdown.js");
      const el = document.createElement("article");
      document.body.append(el);
      const snapshot = {
        course: { id: "course" },
        notes: [{ id: "n" }],
        assets: [],
        sources: [],
        facts: [{ id: "foreign", owner_note_id: "other" }],
      };
      const raw =
        "# Заголовок\n\n**Сильный** и _курсив_.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n$$\\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}$$\n\n$\\frac{a}{b}$ и $\\notARealCommand$\n\n- [x] Готово\n\n<script>window.pwned=1</script>\n\n[bad](javascript:alert(1)) [факт](synopsis://fact/foreign)";
      m.renderMarkdown(el, raw, { snapshot, noteId: "n" });
      const result = {
        heading: el.querySelector("h1").textContent,
        table: el.querySelectorAll("td").length,
        math: el.querySelectorAll(".katex").length,
        formulaError: el.querySelectorAll(".formula-error").length,
        script: el.querySelectorAll("script").length,
        unsafe: el.querySelectorAll('a[href^="javascript:"]').length,
        checked: el.querySelector("input").checked,
        foreignInvalid: el.querySelector(".fact-link") === null,
      };
      m.renderMarkdown(el, "😀 повтор повтор и \\[скобки\\]", {
        snapshot,
        noteId: "n",
      });
      let span = el.querySelector("[data-source-span]");
      let range = document.createRange();
      range.setStart(span.firstChild, 10);
      range.setEnd(span.firstChild, 16);
      window.getSelection().removeAllRanges();
      window.getSelection().addRange(range);
      result.selection = m.getSourceSelection(el);
      m.renderMarkdown(el, "**emphasis** and $x$", { snapshot, noteId: "n" });
      span = el.querySelector("strong [data-source-span]");
      range = document.createRange();
      range.setStart(span.firstChild, 0);
      range.setEnd(span.firstChild, 8);
      window.getSelection().removeAllRanges();
      window.getSelection().addRange(range);
      result.emphasis = m.getSourceSelection(el);
      const escaped = "До \\[скобки\\] &amp; после";
      m.renderMarkdown(el, escaped, { snapshot, noteId: "n" });
      span = el.querySelector("[data-source-span]");
      range = document.createRange();
      range.setStart(span.firstChild, 3);
      range.setEnd(span.firstChild, 11);
      window.getSelection().removeAllRanges();
      window.getSelection().addRange(range);
      const mapped = m.getSourceSelection(el);
      result.escaped = escaped.slice(mapped.raw_start, mapped.raw_end);
      m.renderMarkdown(el, "[Вектор](synopsis://note/n)", {
        snapshot,
        noteId: "n",
      });
      span = el.querySelector("a span");
      range = document.createRange();
      range.selectNodeContents(span.firstChild);
      window.getSelection().removeAllRanges();
      window.getSelection().addRange(range);
      try {
        m.getSourceSelection(el);
        result.refused = false;
      } catch {
        result.refused = true;
      }
      return result;
    });
    assert.equal(checks.heading, "Заголовок");
    assert.equal(checks.table, 2);
    assert.equal(checks.math, 2);
    assert.equal(checks.formulaError, 1);
    assert.equal(checks.script, 0);
    assert.equal(checks.unsafe, 0);
    assert.equal(checks.checked, true);
    assert.equal(checks.foreignInvalid, true);
    assert.deepEqual(checks.selection, {
      raw_start: 10,
      raw_end: 16,
      selected_text: "повтор",
    });
    assert.deepEqual(checks.emphasis, {
      raw_start: 2,
      raw_end: 10,
      selected_text: "emphasis",
    });
    assert.equal(checks.escaped, "\\[скобки\\]");
    assert.equal(checks.refused, true);
  } finally {
    await browser?.close();
    server.kill();
    await once(server, "exit");
  }
});
