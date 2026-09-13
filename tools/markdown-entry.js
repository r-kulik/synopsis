import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import katex from "katex";
import { EditorView } from "@codemirror/view";
import { basicSetup } from "codemirror";
import { markdown } from "@codemirror/lang-markdown";

const parser = unified().use(remarkParse).use(remarkGfm).use(remarkMath);
const documents = new WeakMap();
const internal =
  /^synopsis:\/\/(note|source|fact|asset)\/([a-zA-Z0-9_-]+)(?:\?page=([1-9][0-9]*))?$/;

// UTF-16 boundaries refer to the original raw source, including escapes/entities.
function boundaries(raw, value, start) {
  const result = [start];
  let decoded = "",
    i = 0;
  while (i < raw.length) {
    let text = raw[i],
      length = 1;
    if (
      raw[i] === "\\" &&
      /[!"#$%&'()*+,\-./:;<=>?@[\]\\^_`{|}~]/.test(raw[i + 1] || "")
    ) {
      text = raw[i + 1];
      length = 2;
    } else if (raw[i] === "&") {
      const m = raw
        .slice(i)
        .match(/^&(?:#[xX][0-9a-fA-F]+|#[0-9]+|[a-zA-Z][a-zA-Z0-9]+);/);
      if (m) {
        const el = document.createElement("textarea");
        el.innerHTML = m[0];
        text = el.value;
        length = m[0].length;
      }
    } else {
      const cp = raw.codePointAt(i);
      text = String.fromCodePoint(cp);
      length = text.length;
    }
    decoded += text;
    for (let j = 1; j <= text.length; j++)
      result.push(j === text.length ? start + i + length : null);
    i += length;
  }
  return decoded === value ? result : null;
}

export function renderMarkdown(container, raw, options = {}) {
  const {
    snapshot = { notes: [], sources: [], facts: [], assets: [] },
    courseId = snapshot.course?.id,
    noteId,
  } = options;
  const tree = parser.parse(raw),
    diagnostics = [],
    spans = new Map(),
    definitions = new Map();
  const walk = (node) => {
    if (node.type === "definition")
      definitions.set(node.identifier.toLowerCase(), node);
    for (const c of node.children || []) walk(c);
  };
  walk(tree);
  const lookup = (type, id) =>
    (
      snapshot[
        { note: "notes", source: "sources", fact: "facts", asset: "assets" }[
          type
        ]
      ] || []
    ).find((x) => x.id === id);
  const assetUrl = (id) =>
    `/api/courses/${encodeURIComponent(courseId)}/assets/${encodeURIComponent(id)}`;
  const message = (text, cls = "invalid-link") => {
    const e = document.createElement("span");
    e.className = cls;
    e.textContent = text;
    diagnostics.push(text);
    return e;
  };
  function link(node, image = false) {
    let url = node.url;
    if (node.identifier)
      url = definitions.get(node.identifier.toLowerCase())?.url || "";
    const m = internal.exec(url || "");
    if (image) {
      if (
        m &&
        m[1] === "asset" &&
        !m[3] &&
        lookup("asset", m[2])?.media_type.startsWith("image/")
      ) {
        const img = document.createElement("img");
        img.src = assetUrl(m[2]);
        img.alt = node.alt || "";
        img.loading = "lazy";
        img.addEventListener("error", () =>
          img.replaceWith(
            message(`Изображение недоступно: ${node.alt || "вложение"}`),
          ),
        );
        return img;
      }
      return message(
        `Изображение «${node.alt || "без подписи"}»: ${m ? "вложение не найдено" : "добавьте файл в курс для локального хранения"}`,
        "image-diagnostic",
      );
    }
    const el = document.createElement("a");
    for (const c of node.children || []) el.append(render(c, true));
    if (m) {
      const [, type, id, page] = m,
        target = lookup(type, id);
      if (
        !target ||
        (page && type !== "source") ||
        (type === "fact" && target.owner_note_id !== noteId) ||
        (type === "source" &&
          page &&
          target.page_count &&
          +page > target.page_count)
      ) {
        el.removeAttribute("href");
        el.className = "invalid-link";
        el.title = "Цель ссылки отсутствует в этом конспекте или курсе";
        el.setAttribute("aria-disabled", "true");
        return el;
      }
      el.className = `internal-link ${type}-link`;
      el.dataset.resource = type;
      el.dataset.target = id;
      if (type === "source") {
        el.href = assetUrl(target.asset_id) + (page ? `#page=${page}` : "");
        el.target = "_blank";
        el.rel = "noopener noreferrer";
        el.title = page
          ? `PDF, страница ${page}. Если переход не сработал, введите номер в просмотрщике.`
          : "Открыть PDF в новой вкладке";
        if (options.onSource)
          el.addEventListener("click", (e) => {
            e.preventDefault();
            options.onSource(id, page ? +page : null);
          });
      } else {
        el.href = type === "asset" ? assetUrl(id) : "#";
        el.addEventListener("click", (e) => {
          if (type === "note" || type === "fact") {
            e.preventDefault();
            (type === "note" ? options.onNote : options.onFact)?.(id);
          }
        });
      }
    } else if (/^https?:\/\//i.test(url || "")) {
      el.href = url;
      el.target = "_blank";
      el.rel = "noopener noreferrer";
    } else {
      el.className = "invalid-link";
      el.title = "Небезопасный или некорректный адрес";
      el.setAttribute("aria-disabled", "true");
    }
    return el;
  }
  function render(node, blocked = false) {
    if (node.type === "text") {
      const el = document.createElement("span");
      el.textContent = node.value;
      const start = node.position?.start.offset,
        end = node.position?.end.offset;
      const map =
        !blocked && start !== undefined
          ? boundaries(raw.slice(start, end), node.value, start)
          : null;
      if (map && !/[\r\n]/.test(node.value)) {
        const key = String(spans.size);
        el.dataset.sourceSpan = key;
        spans.set(key, { boundaries: map, text: node.value });
      }
      return el;
    }
    if (node.type === "link" || node.type === "linkReference")
      return link(node);
    if (node.type === "image" || node.type === "imageReference")
      return link(node, true);
    if (node.type === "math" || node.type === "inlineMath") {
      const el = document.createElement(node.type === "math" ? "div" : "span");
      el.className = "math";
      try {
        katex.render(node.value, el, {
          displayMode: node.type === "math",
          throwOnError: true,
          trust: false,
          strict: "warn",
          output: "htmlAndMathml",
          maxExpand: 1000,
        });
      } catch {
        el.textContent = node.value;
        el.className = "formula-error";
        el.title = "Формула содержит неподдержанную команду или ошибку";
        diagnostics.push(el.title);
      }
      return el;
    }
    if (
      node.type === "code" ||
      node.type === "inlineCode" ||
      node.type === "html"
    ) {
      const code = document.createElement("code");
      code.textContent = node.value;
      if (node.type === "inlineCode") return code;
      const pre = document.createElement("pre");
      pre.append(code);
      return pre;
    }
    if (node.type === "definition") return document.createDocumentFragment();
    if (node.type === "table") {
      const table = document.createElement("table"),
        head = document.createElement("thead"),
        body = document.createElement("tbody");
      node.children.forEach((row, i) => {
        const tr = document.createElement("tr");
        row.children.forEach((cell, j) => {
          const td = document.createElement(i ? "td" : "th");
          if (node.align[j]) td.style.textAlign = node.align[j];
          for (const c of cell.children) td.append(render(c, blocked));
          tr.append(td);
        });
        (i ? body : head).append(tr);
      });
      table.append(head, body);
      const wrapper = document.createElement("div");
      wrapper.className = "table-scroll";
      wrapper.append(table);
      return wrapper;
    }
    const tags = {
      root: "div",
      paragraph: "p",
      heading: `h${node.depth}`,
      emphasis: "em",
      strong: "strong",
      delete: "del",
      blockquote: "blockquote",
      list: node.ordered ? "ol" : "ul",
      listItem: "li",
      thematicBreak: "hr",
      break: "br",
    };
    const el = document.createElement(tags[node.type] || "span");
    if (node.type === "list" && node.start && node.start !== 1)
      el.start = node.start;
    if (
      node.type === "listItem" &&
      node.checked !== null &&
      node.checked !== undefined
    ) {
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = node.checked;
      checkbox.disabled = true;
      el.className = "task-list-item";
      el.append(checkbox);
      blocked = true;
    }
    for (const c of node.children || []) {
      // Tight Markdown lists keep their text beside the marker/checkbox.
      if (node.type === "listItem" && !node.spread && c.type === "paragraph") {
        for (const inline of c.children) el.append(render(inline, blocked));
      } else el.append(render(c, blocked));
    }
    return el;
  }
  container.replaceChildren(render(tree));
  container.classList.add("markdown-body");
  documents.set(container, { spans, raw });
  return { diagnostics };
}

export function getSourceSelection(container) {
  const selected = window.getSelection(),
    doc = documents.get(container);
  if (!doc || !selected?.rangeCount || selected.isCollapsed)
    throw Error("Сначала выделите текст в режиме чтения.");
  const range = selected.getRangeAt(0),
    start = range.startContainer,
    end = range.endContainer;
  if (
    start.nodeType !== Node.TEXT_NODE ||
    end.nodeType !== Node.TEXT_NODE ||
    start !== end ||
    !container.contains(start)
  )
    throw Error(
      "Выделите текст внутри одного фрагмента, без перехода между блоками, ссылками или формулами.",
    );
  const span = start.parentElement.closest("[data-source-span]");
  const map = span && doc.spans.get(span.dataset.sourceSpan);
  if (!map)
    throw Error("Внутри ссылок, кода, HTML и формул это действие недоступно.");
  const a = map.boundaries[range.startOffset],
    b = map.boundaries[range.endOffset];
  if (a == null || b == null || a >= b)
    throw Error("Выделение пересекает границу символа.");
  return { raw_start: a, raw_end: b, selected_text: range.toString() };
}

export function mountEditor(
  container,
  { text = "", onChange = () => {} } = {},
) {
  const view = new EditorView({
    doc: text,
    parent: container,
    extensions: [
      basicSetup,
      markdown(),
      EditorView.lineWrapping,
      EditorView.updateListener.of((u) => {
        if (u.docChanged) onChange(u.state.doc.toString());
      }),
      EditorView.theme({
        "&": { height: "100%", fontSize: "14px" },
        ".cm-scroller": { overflow: "auto", fontFamily: "Consolas, monospace" },
        ".cm-content": { padding: "18px 12px" },
        ".cm-focused": { outline: "none" },
      }),
    ],
  });
  return {
    getValue: () => view.state.doc.toString(),
    focus: () => view.focus(),
    destroy: () => view.destroy(),
    insert(value) {
      view.dispatch(view.state.replaceSelection(value));
      view.focus();
    },
  };
}
