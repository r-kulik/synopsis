export const icons = {
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  arrowLeft: "m12 5-7 7 7 7M5 12h14",
  arrowRight: "m12 5 7 7-7 7M5 12h14",
  book: "M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-2H4zM20 4h-4a3 3 0 0 0-3 3v14a4 4 0 0 1 4-2h3z",
  library: "M4 4v16M8 4v16M12 4v16m4-16 4 16",
  upload: "M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5",
  download: "M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5",
  archive: "M3 4h18v4H3zM5 8v12h14V8M10 12h4",
  search: "M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  edit: "m15 4 5 5M3 21l5-1L21 7a2 2 0 0 0-5-5L3 15z",
  paperclip:
    "m9 12 6-6a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2m-4 10-3 3a1 1 0 0 0 2 2l10-10",
  network: "M9 5h6v5H9zM2 16h6v5H2zM16 16h6v5h-6zM12 10v3M5 16v-3h14v3",
  link: "m10 13 4-4M8 15l-2 2a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m2 3 2-2a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0",
  sliders: "M4 7h7m4 0h5M4 17h2m4 0h10M11 4v6M6 14v6",
  maximize: "M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5",
  message: "M21 3H3v14h5l4 4 4-4h5zM7 7h10M7 11h7",
  panel: "M3 4h18v16H3zM9 4v16",
  close: "m6 6 12 12M6 18 18 6",
  check: "m5 12 4 4L19 6",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  file: "M14 2H5v20h14V7zm0 0v5h5M8 12h8M8 16h6",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zm13 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  image: "M3 3h18v18H3zM3 16l5-5 5 5 3-3 5 5M16 7h.01",
  trash: "M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7",
  external: "M14 3h7v7m0-7L10 14M10 3H3v18h18v-7",
  info: "M12 16v-5M12 7h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  concept: "M12 3a7 7 0 0 0-4 13v3h8v-3a7 7 0 0 0-4-13zm-3 19h6",
  example: "m9 3-6 9h6l-1 9 13-13h-8l2-5",
  task: "M8 3H4v18h16V3h-4M8 2h8v4H8zm0 11 3 3 5-6",
  externalConcept: "M14 3h7v7m0-7-9 9M10 3H3v18h18v-7",
  lecture: "M3 4h18v14H3zM8 22l4-4 4 4M7 8h10M7 12h7",
};
export const kinds = {
  lecture: "Лекция",
  concept: "Понятие",
  externalConcept: "Внешнее понятие",
  example: "Пример",
  task: "Задача",
};
export const edgeKinds = {
  contextual: "Контекстная связь",
  hierarchical: "Иерархия понятий",
  mention: "Упоминание",
  exampleAttachment: "Пример к понятию",
  taskAttachment: "Задача к понятию",
};
export function icon(name, cls = "") {
  return `<svg class="icon ${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${icons[name] || icons.file}"/></svg>`;
}
export function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => {
    el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon));
    el.removeAttribute("data-icon");
  });
}
export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];
export const escapeHTML = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export function errorMessage(error) {
  const message = error?.message || String(error);
  const translations = [
    [
      /Failed to fetch|NetworkError/i,
      "Не удалось связаться с приложением. Проверьте, что локальный сервер запущен.",
    ],
    [
      /revision|stale/i,
      "Конспект уже изменился. Ваш черновик сохранён в браузере. Скопируйте его или перезагрузите курс, чтобы сравнить версии.",
    ],
    [
      /compatible|invalid.*edge|edge.*kind/i,
      "Этот тип связи не подходит выбранным карточкам. Проверьте типы конспектов.",
    ],
    [
      /coincident/i,
      "Сначала разнесите карточки на карте: их центры совпадают.",
    ],
    [
      /selection|span|range|overlap/i,
      "Это выделение нельзя безопасно превратить в ссылку. Выделите текст внутри одного абзаца, без формулы, кода или существующей ссылки.",
    ],
    [
      /not found|missing|does not exist/i,
      "Объект не найден. Возможно, он уже был удалён.",
    ],
    [/title.*required|empty.*title/i, "Укажите название."],
  ];
  return (
    translations.find(([pattern]) => pattern.test(message))?.[1] || message
  );
}
export async function api(path, data, options = {}) {
  const response = await fetch(
    path,
    data === undefined
      ? options
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
          ...options,
        },
  );
  if (!response.ok) {
    let detail;
    try {
      detail = await response.json();
    } catch {
      detail = { error: `Ошибка ${response.status}` };
    }
    throw new Error(
      detail.error || detail.message || `Ошибка ${response.status}`,
    );
  }
  return response.status === 204 ? null : response.json();
}
export function toast(message, type = "success") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `${icon(type === "error" ? "info" : "check")}<span>${escapeHTML(message)}</span><button class="icon-button" aria-label="Закрыть">${icon("close")}</button>`;
  $("#toast-region").append(el);
  while ($("#toast-region").children.length > 3)
    $("#toast-region").firstElementChild.remove();
  $("button", el).addEventListener("click", () => el.remove());
  setTimeout(() => el.remove(), 6000);
}
export function report(error) {
  console.error(error);
  toast(errorMessage(error), "error");
}
export function modal({
  title,
  description = "",
  body = "",
  submit = "Сохранить",
  danger = false,
  wide = false,
  onSubmit,
}) {
  const dialog = document.createElement("dialog");
  dialog.className = `modal ${wide ? "wide" : ""}`;
  dialog.innerHTML = `<form><div class="modal-heading"><div><h2>${escapeHTML(title)}</h2>${description ? `<p>${escapeHTML(description)}</p>` : ""}</div><button class="icon-button modal-close" type="button" aria-label="Закрыть">${icon("close")}</button></div><div class="modal-body">${body}</div><div class="alert error form-error hidden" role="alert"></div><div class="modal-footer"><button type="button" class="button ghost cancel">Отмена</button>${submit ? `<button type="submit" class="button ${danger ? "danger" : "primary"}">${escapeHTML(submit)}</button>` : ""}</div></form>`;
  document.body.append(dialog);
  // Menu actions live inside the dialog form, but must never submit it.
  $$("button:not([type])", dialog).forEach((button) => {
    button.type = "button";
  });
  const dialogId = `dialog-${crypto.randomUUID()}`;
  $("h2", dialog).id = dialogId;
  dialog.setAttribute("aria-labelledby", dialogId);
  $$("label.field", dialog).forEach((label, index) => {
    const caption = label.querySelector(":scope > span");
    const control = label.querySelector("input, select, textarea");
    if (!caption || !control) return;
    caption.id = `${dialogId}-label-${index}`;
    control.setAttribute("aria-labelledby", caption.id);
    const hint = label.querySelector("small");
    if (hint) {
      hint.id ||= `${dialogId}-hint-${index}`;
      control.setAttribute("aria-describedby", hint.id);
    }
  });
  hydrateIcons(dialog);
  const close = () => {
    dialog.close();
    dialog.remove();
  };
  $(".modal-close", dialog).addEventListener("click", close);
  $(".cancel", dialog).addEventListener("click", close);
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) {
      const r = dialog.getBoundingClientRect();
      if (
        e.clientX < r.left ||
        e.clientX > r.right ||
        e.clientY < r.top ||
        e.clientY > r.bottom
      )
        close();
    }
  });
  $("form", dialog).addEventListener("submit", async (e) => {
    e.preventDefault();
    const button = $("[type=submit]", dialog);
    if (!button || !onSubmit || button.disabled) return;
    button.disabled = true;
    const old = button.textContent;
    button.textContent = "Сохраняем…";
    $(".form-error", dialog).classList.add("hidden");
    try {
      const shouldClose = await onSubmit(new FormData(e.target), dialog);
      if (shouldClose !== false) close();
    } catch (error) {
      const alert = $(".form-error", dialog);
      alert.textContent = errorMessage(error);
      alert.classList.remove("hidden");
    } finally {
      button.disabled = false;
      button.textContent = old;
    }
  });
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  dialog.showModal();
  return dialog;
}
export function confirmAction(title, description, label, action) {
  return modal({
    title,
    description,
    submit: label,
    danger: true,
    onSubmit: action,
  });
}
export function field(label, name, value = "", options = {}) {
  const hint = options.hint ? `<small>${escapeHTML(options.hint)}</small>` : "";
  const attrs = `name="${name}" ${options.required ? "required" : ""} ${options.maxlength ? `maxlength="${options.maxlength}"` : ""}`;
  return `<label class="field"><span>${escapeHTML(label)}</span>${options.textarea ? `<textarea ${attrs} rows="${options.rows || 4}" placeholder="${escapeHTML(options.placeholder || "")}">${escapeHTML(value)}</textarea>` : `<input ${attrs} type="${options.type || "text"}" value="${escapeHTML(value)}" placeholder="${escapeHTML(options.placeholder || "")}" ${options.min ? `min="${options.min}"` : ""}>`}${hint}</label>`;
}
export function kindOptions(selected = "concept", includeLecture = true) {
  return Object.entries(kinds)
    .filter(([key]) => includeLecture || key !== "lecture")
    .map(
      ([key, label]) =>
        `<option value="${key}" ${selected === key ? "selected" : ""}>${label}</option>`,
    )
    .join("");
}
export async function upload(path, file) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": file.type || "application/octet-stream",
      "X-Filename": encodeURIComponent(file.name),
    },
    body: file,
  });
  if (!response.ok) {
    let data;
    try {
      data = await response.json();
    } catch {}
    throw new Error(data?.error || "Не удалось загрузить файл");
  }
  return response.json();
}
hydrateIcons();
