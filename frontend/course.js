import {
  $,
  $$,
  escapeHTML as h,
  icon,
  kinds,
  edgeKinds,
  api,
  upload,
  modal,
  field,
  kindOptions,
  confirmAction,
  toast,
  report as reportError,
  errorMessage,
} from "./common.js";
import { CourseMap, cardPalette, linePalette } from "./map.js";
import { renderMarkdown, getSourceSelection, mountEditor } from "./markdown.js";

const courseId = decodeURIComponent(
  location.pathname.split("/").filter(Boolean)[1] || "",
);
const base = `/api/courses/${encodeURIComponent(courseId)}`;
const storageKey = `synopsis.drafts.${courseId}`;
const state = {
  snapshot: null,
  tabs: [],
  active: null,
  editor: null,
  selection: null,
  catalog: "notes",
  busy: 0,
};
let persistTimer;
const noteById = (id) => state.snapshot?.notes.find((n) => n.id === id);
const tabById = (id) => state.tabs.find((t) => t.id === id);
const activeTab = () => tabById(state.active);
const dirty = (tab) => tab.text !== tab.savedText;
const cardFor = (id) => state.snapshot.cards.find((c) => c.note_id === id);
const boxFor = (id) =>
  state.snapshot.lecture_boxes.find((b) => b.note_id === id);
const map = new CourseMap({
  svg: $("#course-map"),
  onOpen: openNote,
  onCommand: mapCommand,
});

function report(error) {
  if (!error?.recoveryShown) reportError(error);
}
function pausedForConflict() {
  const error = new Error(
    "Сохранение приостановлено. Сравните версии и выберите, какой текст оставить. После этого сохраните конспект отдельным действием.",
  );
  error.recoveryShown = true;
  return error;
}

async function compareNoteVersions(id) {
  const tab = tabById(id);
  if (!tab) return;
  if (tab.conflictDialog?.open) {
    tab.conflictDialog.focus();
    return;
  }
  if (tab.conflictLoading) return;
  tab.conflictLoading = true;
  try {
    let latestSnapshot = await api(base);
    if (tabById(id) !== tab) return;
    let latest = latestSnapshot.notes.find((note) => note.id === id);
    if (!latest)
      throw new Error(
        "Конспект больше не найден в курсе. Ваш черновик сохранён в браузере: скопируйте его текст перед закрытием вкладки.",
      );
    const dialog = modal({
      title: "Сохранённая версия изменилась",
      description: `«${latest.title}». Сравните текст курса с вашим черновиком и выберите, с какой версией продолжить.`,
      wide: true,
      submit: null,
      body: `<div class="field-row"><label class="field"><span>Сохранено в курсе</span><textarea name="saved_version" data-conflict-saved rows="10" readonly spellcheck="false">${h(latest.markdown)}</textarea><small>Текст, полученный из курса сейчас.</small></label><label class="field"><span>Ваш локальный черновик</span><textarea name="local_draft" data-conflict-draft rows="10" readonly spellcheck="false">${h(tab.text)}</textarea><small>Можно выделить и скопировать перед выбором.</small></label></div><div class="alert hidden" data-conflict-status role="status"></div><div class="field"><span>Продолжить с сохранённым текстом</span><small>Загрузит версию курса и заменит ею ваш локальный черновик. Несохранённые изменения из правого поля будут отброшены.</small><button type="button" class="button secondary" data-conflict-load>Загрузить сохранённую версию</button></div><div class="field"><span>Продолжить с моим текстом</span><small>Оставит ваш черновик для редактирования. Следующее нажатие «Сохранить» заменит им показанный текст курса; сейчас запись в курс не выполняется.</small><button type="button" class="button primary" data-conflict-keep>Оставить мой черновик</button></div>`,
    });
    tab.conflictDialog = dialog;
    dialog.addEventListener(
      "close",
      () => {
        delete tab.conflictDialog;
      },
      { once: true },
    );
    const choose = async (keepDraft) => {
      const buttons = $$("[data-conflict-load], [data-conflict-keep]", dialog);
      buttons.forEach((button) => (button.disabled = true));
      try {
        const checkedSnapshot = await api(base);
        if (!dialog.open || !dialog.isConnected) return;
        const checked = checkedSnapshot.notes.find((note) => note.id === id);
        if (!checked)
          throw new Error(
            "Конспект удалён из курса. Ваш черновик остаётся в правом поле — скопируйте его перед закрытием.",
          );
        if (checked.revision !== latest.revision) {
          latestSnapshot = checkedSnapshot;
          latest = checked;
          $("[data-conflict-saved]", dialog).value = latest.markdown;
          const status = $("[data-conflict-status]", dialog);
          status.textContent =
            "Курс снова обновился, пока вы сравнивали тексты. Слева показана новая сохранённая версия. Проверьте её и повторите выбор.";
          status.classList.remove("hidden");
          return;
        }
        latestSnapshot = checkedSnapshot;
        latest = checked;
        if (!keepDraft) tab.text = latest.markdown;
        tab.savedText = latest.markdown;
        tab.revision = latest.revision;
        tab.mode = keepDraft ? "edit" : "read";
        state.snapshot = latestSnapshot;
        state.active = id;
        $("#sidebar-course-title").textContent = latestSnapshot.course.title;
        $("#topbar-course-title").textContent = latestSnapshot.course.title;
        document.title = latestSnapshot.course.title + " — Synopsis";
        hideSelection();
        persistDrafts();
        refreshChrome();
        renderSources();
        renderEditor();
        dialog.close();
        toast(
          keepDraft
            ? "Черновик оставлен. Нажмите «Сохранить», чтобы записать его в курс."
            : "Загружена сохранённая версия. Локальный черновик заменён.",
        );
      } catch (error) {
        const alert = $(".form-error", dialog);
        alert.textContent = errorMessage(error);
        alert.classList.remove("hidden");
      } finally {
        buttons.forEach((button) => (button.disabled = false));
      }
    };
    $("[data-conflict-load]", dialog).addEventListener("click", () =>
      choose(false),
    );
    $("[data-conflict-keep]", dialog).addEventListener("click", () =>
      choose(true),
    );
  } finally {
    delete tab.conflictLoading;
  }
}

function persistDrafts() {
  clearTimeout(persistTimer);
  try {
    localStorage.setItem(
      storageKey,
      JSON.stringify({
        active: state.active,
        tabs: state.tabs.map(({ id, text, revision, savedText, mode }) => ({
          id,
          text,
          revision,
          savedText,
          mode,
        })),
      }),
    );
  } catch {
    toast(
      "Браузер не смог сохранить резервную копию черновика. Сохраните конспект в курс.",
      "error",
    );
  }
}
function schedulePersist() {
  clearTimeout(persistTimer);
  persistTimer = setTimeout(persistDrafts, 350);
}
function renderSaveState() {
  const changed = state.tabs.filter(dirty).length;
  $("#save-state").classList.toggle("unsaved", changed > 0);
  $("#save-state").innerHTML =
    `<span class="local-dot"></span>${state.busy ? "Сохраняем…" : changed ? "Есть несохранённый черновик" : "Все изменения сохранены"}`;
}
function refreshChrome() {
  renderCatalog();
  renderTabs();
  map.update(state.snapshot, state.active);
  renderSaveState();
}
async function refresh({ editor = false } = {}) {
  state.snapshot = await api(base);
  $("#sidebar-course-title").textContent = state.snapshot.course.title;
  $("#topbar-course-title").textContent = state.snapshot.course.title;
  document.title = state.snapshot.course.title + " — Synopsis";
  state.tabs = state.tabs.filter((t) => noteById(t.id));
  if (!tabById(state.active)) state.active = state.tabs.at(-1)?.id || null;
  refreshChrome();
  renderSources();
  if (editor) renderEditor();
}
async function mapCommand(name, data) {
  if (name) await api(`${base}/map/${name}`, data);
  await refresh();
}
function restoreDrafts() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || "{}");
    for (const item of saved.tabs || []) {
      const note = noteById(item.id);
      if (!note) continue;
      const hasDraft = item.text !== item.savedText;
      state.tabs.push({
        id: note.id,
        text: hasDraft ? item.text : note.markdown,
        savedText: hasDraft ? item.savedText : note.markdown,
        revision: hasDraft ? item.revision : note.revision,
        mode: hasDraft ? "edit" : item.mode || "read",
      });
    }
    state.active = tabById(saved.active)
      ? saved.active
      : state.tabs.at(-1)?.id || null;
    if (state.tabs.some(dirty))
      toast("Восстановлены ваши несохранённые черновики");
  } catch {
    /* Corrupt browser cache never prevents opening course data. */
  }
}
function openNote(id) {
  const note = noteById(id);
  if (!note) {
    toast("Этот конспект удалён или не принадлежит курсу.", "error");
    return;
  }
  if (!tabById(id))
    state.tabs.push({
      id,
      text: note.markdown,
      savedText: note.markdown,
      revision: note.revision,
      mode: "read",
    });
  state.active = id;
  hideSelection();
  refreshChrome();
  renderEditor();
  schedulePersist();
}
function renderCatalog() {
  const query = $("#note-search").value.trim().toLocaleLowerCase(),
    kind = $("#note-kind-filter").value,
    cardless = $("#cardless-filter").checked,
    notes = state.snapshot.notes.filter(
      (n) =>
        (!query ||
          [n.title, n.summary, n.markdown].some((t) =>
            t.toLocaleLowerCase().includes(query),
          )) &&
        (!kind || n.kind === kind) &&
        (!cardless || (!cardFor(n.id) && !boxFor(n.id))),
    );
  $("#notes-count").textContent = notes.length;
  $("#notes-list").innerHTML = notes.length
    ? notes
        .map(
          (note) =>
            `<button class="note-list-item ${state.active === note.id ? "active" : ""}" data-note-id="${h(note.id)}" title="${h(note.title)}"><span class="note-kind-icon ${note.kind}">${icon(note.kind)}</span><span><strong>${h(note.title)}</strong><small>${h(kinds[note.kind])}${note.summary ? " · " + h(note.summary) : ""}</small></span>${!cardFor(note.id) && !boxFor(note.id) ? '<i class="cardless-mark" title="Без карточки"></i>' : ""}</button>`,
        )
        .join("")
    : `<div class="empty-state">${icon(query || kind || cardless ? "search" : "file")}<strong>${query || kind || cardless ? "Ничего не найдено" : "Пока чистый лист"}</strong>${query || kind || cardless ? "Попробуйте другой запрос или снимите фильтр." : "Создайте первую лекцию или понятие — они появятся здесь."}</div>`;
  $$(".note-list-item", $("#notes-list")).forEach((button) =>
    button.addEventListener("click", () => openNote(button.dataset.noteId)),
  );
}
function renderTabs() {
  $("#note-tabs").innerHTML = state.tabs
    .map((tab) => {
      const note = noteById(tab.id);
      return `<div class="note-tab ${tab.id === state.active ? "active" : ""}" role="tab" aria-selected="${tab.id === state.active}" tabindex="${tab.id === state.active ? "0" : "-1"}" data-tab="${h(tab.id)}">${icon(note.kind)}<span title="${h(note.title)}">${h(note.title)}</span>${dirty(tab) ? '<i class="dirty-indicator" title="Есть черновик"></i>' : ""}<button class="icon-button" data-close-tab="${h(tab.id)}" aria-label="Закрыть вкладку ${h(note.title)}">${icon("close")}</button></div>`;
    })
    .join("");
  $$("[data-tab]", $("#note-tabs")).forEach((el) => {
    el.addEventListener("click", (e) => {
      if (!e.target.closest("[data-close-tab]")) openNote(el.dataset.tab);
    });
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openNote(el.dataset.tab);
      }
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        const index = state.tabs.findIndex((t) => t.id === el.dataset.tab),
          next =
            state.tabs[
              (index + (e.key === "ArrowRight" ? 1 : -1) + state.tabs.length) %
                state.tabs.length
            ];
        openNote(next.id);
        $("[aria-selected=true]", $("#note-tabs")).focus();
      }
    });
  });
  $$("[data-close-tab]", $("#note-tabs")).forEach((el) =>
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      closeTab(el.dataset.closeTab);
    }),
  );
}
function removeTab(id) {
  const index = state.tabs.findIndex((t) => t.id === id);
  state.tabs = state.tabs.filter((t) => t.id !== id);
  if (state.active === id)
    state.active =
      state.tabs[Math.min(index, state.tabs.length - 1)]?.id || null;
  refreshChrome();
  renderEditor();
  persistDrafts();
}
function closeTab(id) {
  const tab = tabById(id);
  if (!dirty(tab)) {
    removeTab(id);
    return;
  }
  const dialog = modal({
    title: "В конспекте остались изменения",
    description:
      "Черновик «" + noteById(id).title + "» ещё не сохранён в курс.",
    submit: null,
    body: `<p class="subtle-note">Вы можете сохранить его сейчас или закрыть вкладку без этих изменений.</p><div class="dirty-dialog-actions"><button type="button" class="button primary" data-draft-save>Сохранить и закрыть</button><button type="button" class="button secondary" data-draft-discard>Отбросить черновик</button></div>`,
  });
  $("[data-draft-save]", dialog).addEventListener("click", async () => {
    try {
      await saveTab(id);
      while (dirty(tab)) await saveTab(id);
      dialog.close();
      removeTab(id);
    } catch (error) {
      report(error);
    }
  });
  $("[data-draft-discard]", dialog).addEventListener("click", () => {
    dialog.close();
    removeTab(id);
  });
}
async function saveTab(id = state.active) {
  const tab = tabById(id);
  if (!tab) return;
  if (tab.saving) return tab.saving;
  if (tab.conflictDialog?.open || tab.conflictLoading)
    throw pausedForConflict();
  if (!dirty(tab)) {
    tab.mode = "read";
    if (id === state.active) renderEditor();
    return;
  }
  const submittedText = tab.text,
    submittedRevision = tab.revision;
  state.busy++;
  refreshChrome();
  tab.saving = (async () => {
    try {
      const result = await api(`${base}/notes/${encodeURIComponent(id)}/save`, {
        markdown: submittedText,
        revision: submittedRevision,
      });
      tab.revision = result.revision;
      tab.savedText = submittedText;
      if (tab.text === submittedText) tab.mode = "read";
      await refresh({ editor: true });
      persistDrafts();
      toast(
        dirty(tab)
          ? "Версия сохранена. Новые изменения остаются в черновике."
          : "Конспект сохранён",
      );
    } catch (error) {
      if (/revision|stale/i.test(error.message || "")) {
        persistDrafts();
        await compareNoteVersions(id);
        throw pausedForConflict();
      }
      throw error;
    } finally {
      delete tab.saving;
      state.busy--;
      refreshChrome();
    }
  })();
  return tab.saving;
}
function switchMode(mode) {
  const tab = activeTab();
  if (!tab) return;
  tab.mode = mode;
  hideSelection();
  renderEditor();
  schedulePersist();
}
function renderEditor() {
  if (state.editor) {
    state.editor.destroy();
    state.editor = null;
  }
  const note = noteById(state.active),
    tab = activeTab(),
    content = $("#note-content");
  $("#editor-empty").classList.toggle("hidden", !!note);
  content.classList.toggle("hidden", !note);
  if (!note) {
    content.innerHTML = "";
    return;
  }
  const onMap = !!cardFor(note.id) || !!boxFor(note.id),
    lecture = noteById(note.defined_in_lecture_note_id),
    facts = state.snapshot.facts.filter((f) => f.owner_note_id === note.id),
    attached = state.snapshot.lecture_source_attachments.filter(
      (a) => a.lecture_note_id === note.id,
    );
  content.innerHTML = `<div class="note-toolbar"><div class="mode-switch"><button data-mode="read" class="${tab.mode === "read" ? "active" : ""}">${icon("eye")}Чтение</button><button data-mode="edit" class="${tab.mode === "edit" ? "active" : ""}">${icon("edit")}Markdown</button></div><div class="actions">${tab.mode === "edit" || dirty(tab) ? `<button id="save-note" class="button primary small">Сохранить</button>` : ""}<button id="locate-note" class="icon-button" title="${onMap ? "Найти на карте" : "Показать на карте"}" aria-label="${onMap ? "Найти на карте" : "Показать на карте"}">${icon("network")}</button><button id="note-menu" class="icon-button" title="Действия с конспектом" aria-label="Действия с конспектом">${icon("more")}</button></div></div><div class="note-scroll"><div class="note-heading"><span class="note-badge">${icon(note.kind)}${h(kinds[note.kind])}</span><h1>${h(note.title)}</h1>${note.summary ? `<p class="note-summary">${h(note.summary)}</p>` : ""}<div class="note-heading-meta">${icon(onMap ? "network" : "file")}<span>${onMap ? "На карте курса" : "Конспект без карточки"}${lecture ? " · " + h(lecture.title) : ""}</span>${dirty(tab) ? "<span> · Черновик</span>" : ""}</div></div>${tab.mode === "read" ? '<div class="note-reader" id="note-reader"></div><div id="render-diagnostics" class="render-diagnostics hidden"></div>' : '<div class="markdown-editor-wrap"><div class="editor-tools"><button type="button" data-insert="bold" title="Полужирный"><strong>B</strong></button><button type="button" data-insert="italic" title="Курсив"><em>I</em></button><button type="button" data-insert="heading" title="Заголовок">H2</button><button type="button" data-insert="list" title="Список">≡</button><button type="button" data-insert="math" title="Формула">∑</button><button type="button" data-insert="image" title="Добавить изображение">' + icon("image") + '</button><span>Markdown · LaTeX</span></div><div class="markdown-editor" id="markdown-editor"></div><p class="editor-hint">Ctrl + S — сохранить. Изображения добавляются в курс. Черновик остаётся при переключении вкладок.</p></div>'}<div class="note-bottom"><details id="facts-details"><summary>${icon("message")}Факты и комментарии<span>${facts.length}</span></summary><div class="facts-list">${facts.length ? facts.map((f) => `<div class="fact-row"><div><p>${h(f.markdown || "Пустой комментарий")}</p><small>${tab.text.includes(`synopsis://fact/${f.id}`) ? "Привязан к тексту" : "Без привязки · выделите текст, чтобы прикрепить снова"}</small></div><button class="icon-button" data-edit-fact="${h(f.id)}" aria-label="Редактировать факт">${icon("edit")}</button></div>`).join("") : '<p class="empty-state">В режиме чтения выделите фрагмент и выберите «Факт». Комментарий останется связан с вашим текстом.</p>'}</div></details>${
    note.kind === "lecture"
      ? `<details><summary>${icon("paperclip")}Источники лекции<span>${attached.length}</span></summary><div class="facts-list">${attached
          .map((a) => {
            const source = state.snapshot.sources.find(
              (s) => s.id === a.source_id,
            );
            return source
              ? `<button class="source-open-link" data-open-source="${h(source.id)}" data-page="${a.page || ""}">${icon("external")}${h(source.title)}${a.page ? " · стр. " + a.page : ""}</button>`
              : "";
          })
          .join(
            "",
          )}<button class="button ghost small" id="attach-lecture-source">${icon("paperclip")}Прикрепить PDF</button></div></details>`
      : ""
  }</div></div>`;
  if (tab.revision !== note.revision) {
    const warning = document.createElement("div");
    warning.className = "alert";
    warning.style.margin = "0 24px 16px";
    warning.innerHTML = `Сохранённый текст этого конспекта обновился. Сравните его с вашим локальным текстом. <button type="button" class="text-button" data-compare-versions>Сравнить версии</button>`;
    $(".note-heading", content).after(warning);
    $("[data-compare-versions]", warning).addEventListener("click", () =>
      compareNoteVersions(note.id).catch(report),
    );
  }
  $$("[data-mode]", content).forEach((el) =>
    el.addEventListener("click", () => switchMode(el.dataset.mode)),
  );
  $("#save-note")?.addEventListener("click", () => saveTab().catch(report));
  $("#note-menu").addEventListener("click", () => noteMenu(note));
  $("#locate-note").addEventListener("click", () => showOnMap(note));
  $$("[data-edit-fact]", content).forEach((el) =>
    el.addEventListener("click", () => editFact(el.dataset.editFact)),
  );
  $$("[data-open-source]", content).forEach((el) =>
    el.addEventListener("click", () =>
      openSource(el.dataset.openSource, Number(el.dataset.page) || null),
    ),
  );
  $("#attach-lecture-source")?.addEventListener("click", () =>
    attachSourceDialog(note.id),
  );
  if (tab.mode === "read") {
    const reader = $("#note-reader");
    if (!tab.text) {
      reader.innerHTML = `<div class="note-reader-empty">${icon("edit")}Здесь появится ваш конспект.<br>Перейдите в Markdown, чтобы добавить текст или формулы.<br><button class="button ghost small" id="write-note">Начать писать</button></div>`;
      $("#write-note").addEventListener("click", () => switchMode("edit"));
    } else {
      try {
        const rendered = renderMarkdown(reader, tab.text, {
          courseId,
          noteId: note.id,
          snapshot: state.snapshot,
          onNote: openNote,
          onFact: showFact,
          onSource: openSource,
        });
        if (rendered?.diagnostics?.length) {
          $("#render-diagnostics").textContent = rendered.diagnostics
            .map((d) => d.message || d)
            .join(" · ");
          $("#render-diagnostics").classList.remove("hidden");
        }
      } catch (error) {
        reader.textContent = tab.text;
        toast(
          "Не удалось отобразить форматирование. Исходный текст доступен в редакторе.",
          "error",
        );
      }
      reader.addEventListener("mouseup", () => setTimeout(captureSelection, 0));
      reader.addEventListener("keyup", () => setTimeout(captureSelection, 0));
    }
  } else {
    state.editor = mountEditor($("#markdown-editor"), {
      text: tab.text,
      onChange: (text) => {
        tab.text = text;
        schedulePersist();
        renderTabs();
        renderSaveState();
      },
    });
    $$("[data-insert]", content).forEach((el) =>
      el.addEventListener("click", () => insertMarkup(el.dataset.insert)),
    );
  }
}
function insertMarkup(type) {
  if (!state.editor) return;
  const snippets = {
    bold: "**выделенный текст**",
    italic: "*выделенный текст*",
    heading: "\n## Заголовок\n",
    list: "\n- Пункт списка\n",
    math: "\n$$\nx^2 + y^2 = r^2\n$$\n",
  };
  if (type === "image") {
    $("#image-input").click();
    return;
  }
  state.editor.insert(snippets[type] || "");
  state.editor.focus();
}

function noteForm({ selection = null } = {}) {
  const lectureOptions = state.snapshot.notes
    .filter((n) => n.kind === "lecture")
    .map((n) => `<option value="${h(n.id)}">${h(n.title)}</option>`)
    .join("");
  const dialog = modal({
    title: selection ? "Из фрагмента — в новую идею" : "Новый конспект",
    description: selection
      ? "Создадим конспект, карточку и ссылку в выбранном фрагменте."
      : "Выберите форму для вашей идеи. Содержимое всегда можно дополнить.",
    wide: true,
    submit: "Создать конспект",
    body: `${selection ? `<div class="selection-quote">${h(selection.selected_text)}</div>` : ""}<div class="field-row"><label class="field"><span>Тип конспекта</span><select name="kind">${kindOptions("concept", !selection)}</select></label><label class="field" data-lecture-field><span>Лекция определения</span><select name="lecture_note_id"><option value="">Вне лекции</option>${lectureOptions}</select></label></div>${field("Название", "title", selection?.selected_text || "", { required: true, maxlength: 300, placeholder: "О чём этот конспект?" })}${field("Краткое описание", "summary", "", { textarea: true, rows: 2, placeholder: "Одна-две фразы для карточки на карте" })}${!selection ? field("Текст конспекта · Markdown", "markdown", "", { textarea: true, rows: 5, placeholder: "Запишите мысль или вставьте готовый Markdown…" }) : ""}${!selection ? '<label class="checkbox-label" data-card-field><input type="checkbox" name="with_card" checked> Создать карточку на карте</label>' : ""}`,
    onSubmit: async (data) => {
      const kind = data.get("kind"),
        payload = {
          kind,
          title: data.get("title").trim(),
          summary: data.get("summary"),
          markdown: data.get("markdown") || "",
          with_card: data.has("with_card"),
          lecture_note_id:
            kind === "concept" ? data.get("lecture_note_id") || null : null,
          position:
            kind === "concept" && data.get("lecture_note_id")
              ? null
              : map.freePosition(),
        };
      let id;
      if (selection) {
        const result = await api(`${base}/selection/create-note`, {
          ...selection,
          ...payload,
          position: payload.position,
        });
        id = result.id;
        await syncSelectionOwner(selection.note_id);
      } else if (kind === "lecture") {
        const result = await api(`${base}/lectures`, {
          title: payload.title,
          summary: payload.summary,
          markdown: payload.markdown,
          position: payload.position,
        });
        id = result.note_id;
      } else {
        id = (await api(`${base}/notes`, payload)).id;
      }
      await refresh();
      if (id) {
        openNote(id);
        map.focusNote(id);
      }
      toast(
        selection ? "Конспект создан, ссылка добавлена" : "Конспект создан",
      );
    },
  });
  $("[name=kind]", dialog).addEventListener("change", (e) => {
    const kind = e.target.value;
    $("[data-lecture-field]", dialog).classList.toggle(
      "hidden",
      kind !== "concept",
    );
    $("[data-card-field]", dialog)?.classList.toggle(
      "hidden",
      kind === "lecture",
    );
  });
}
function noteMenu(note) {
  const card = cardFor(note.id),
    box = boxFor(note.id),
    dialog = modal({
      title: note.title,
      description: kinds[note.kind],
      submit: null,
      body: `<div class="menu-actions"><button class="nav-item" data-note-action="meta">${icon("edit")}Название и описание</button><button class="nav-item" data-note-action="map">${icon("network")}${card || box ? "Найти на карте" : "Показать на карте"}</button>${card ? `<button class="nav-item" data-note-action="assign">${icon("lecture")}Переместить в лекцию</button><button class="nav-item" data-note-action="remove-card">${icon("eye")}Убрать карточку с карты</button>` : ""}${box ? `<button class="nav-item" data-note-action="remove-box">${icon("eye")}Убрать рамку лекции</button>` : ""}<button class="nav-item danger-text" data-note-action="delete">${icon("trash")}Удалить конспект</button></div>`,
    });
  $$("[data-note-action]", dialog).forEach((el) =>
    el.addEventListener("click", () => {
      dialog.close();
      switch (el.dataset.noteAction) {
        case "meta":
          editNoteMeta(note);
          break;
        case "map":
          showOnMap(note);
          break;
        case "assign":
          assignCardDialog(card);
          break;
        case "remove-card":
          confirmAction(
            "Убрать карточку с карты?",
            "Конспект и ссылки на него сохранятся. Связи этой карточки будут удалены. Карточку можно вернуть из списка конспектов.",
            "Убрать карточку",
            async () => {
              await mapCommand("remove-card", { card_id: card.id });
              renderEditor();
              toast("Карточка убрана. Конспект сохранён.");
            },
          );
          break;
        case "remove-box":
          confirmAction(
            "Убрать рамку лекции?",
            "Преамбула, карточки внутри рамки и их связи сохранятся. Карточки останутся на прежних местах.",
            "Убрать рамку",
            async () => {
              await mapCommand("remove-box", { box_id: box.id });
              renderEditor();
              toast("Рамка убрана. Конспекты сохранены.");
            },
          );
          break;
        case "delete":
          deleteNote(note);
          break;
      }
    }),
  );
}
function editNoteMeta(note) {
  const lectures = state.snapshot.notes.filter(
    (n) => n.kind === "lecture" && n.id !== note.id,
  );
  modal({
    title: "Название и описание",
    body: `${field("Название", "title", note.title, { required: true, maxlength: 300 })}${field("Краткое описание", "summary", note.summary, { textarea: true, rows: 3 })}${note.kind === "concept" ? `<label class="field"><span>Лекция определения</span><select name="defined_in_lecture_note_id"><option value="">Вне лекции</option>${lectures.map((n) => `<option value="${h(n.id)}" ${note.defined_in_lecture_note_id === n.id ? "selected" : ""}>${h(n.title)}</option>`).join("")}</select></label>` : ""}`,
    onSubmit: async (data) => {
      const tab = tabById(note.id);
      if (tab && dirty(tab)) await saveTab(note.id);
      await api(`${base}/notes/${note.id}/meta`, {
        title: data.get("title").trim(),
        summary: data.get("summary"),
        ...(note.kind === "concept"
          ? {
              defined_in_lecture_note_id:
                data.get("defined_in_lecture_note_id") || null,
            }
          : {}),
      });
      await refresh({ editor: true });
      if (tab) tab.revision = noteById(note.id).revision;
      toast("Изменения сохранены");
    },
  });
}
function deleteNote(note) {
  const incoming = state.snapshot.notes.filter((n) =>
    n.markdown.includes(`synopsis://note/${note.id}`),
  ).length;
  confirmAction(
    "Удалить конспект «" + note.title + "»?",
    `Текст конспекта, его карточка и факты будут удалены.${incoming ? " Конспект упоминается в " + incoming + " других конспектах: ссылки останутся в тексте как неработающие." : ""}${note.kind === "lecture" ? " Содержимое лекции сохранится отдельными конспектами." : ""} Это действие нельзя отменить.`,
    "Удалить конспект",
    async () => {
      await api(`${base}/notes/${note.id}/delete`, {});
      removeTab(note.id);
      await refresh({ editor: true });
      toast("Конспект удалён");
    },
  );
}
async function showOnMap(note) {
  try {
    if (!cardFor(note.id) && !boxFor(note.id)) {
      await mapCommand("show-card", {
        note_id: note.id,
        position: map.freePosition(),
      });
      renderEditor();
      toast(
        note.kind === "lecture"
          ? "Рамка лекции восстановлена"
          : "Карточка восстановлена",
      );
    }
    const hidden = state.snapshot.course.settings?.map?.hiddenNoteKinds || [];
    if (hidden.includes(note.kind)) {
      toast(
        "Этот тип скрыт в настройках карты. Включите его в «Оформление и видимость».",
        "error",
      );
      return;
    }
    map.focusNote(note.id);
  } catch (error) {
    report(error);
  }
}
function assignCardDialog(card) {
  modal({
    title: "Карточка в лекции",
    description: "Перемещение рамки будет переносить карточку вместе с ней.",
    body: `<label class="field"><span>Рамка лекции</span><select name="box_id"><option value="">Вне рамки</option>${state.snapshot.lecture_boxes.map((box) => `<option value="${h(box.id)}" ${card.lecture_box_id === box.id ? "selected" : ""}>${h(noteById(box.note_id)?.title || "Лекция")}</option>`).join("")}</select><small>Положение карточки на карте не меняется. Перетащите её в нужное место рамки.</small></label>`,
    onSubmit: async (data) => {
      await mapCommand("assign-card", {
        card_id: card.id,
        box_id: data.get("box_id") || null,
      });
      renderEditor();
      toast("Принадлежность карточки сохранена");
    },
  });
}

function edgeForm() {
  if (state.snapshot.cards.length < 2) {
    toast("Для связи нужны хотя бы две карточки на карте.", "error");
    return;
  }
  const cards = state.snapshot.cards
      .map((c) => ({ card: c, note: noteById(c.note_id) }))
      .filter((x) => x.note),
    options = cards
      .map(
        ({ card, note }) =>
          `<option value="${h(card.id)}">${h(note.title)} · ${h(kinds[note.kind])}</option>`,
      )
      .join("");
  const dialog = modal({
    title: "Соедините две идеи",
    description: "Связи помогают объяснить отношения между карточками курса.",
    wide: true,
    submit: "Создать связь",
    body: `<label class="field"><span>Тип связи</span><select name="kind">${Object.entries(
      edgeKinds,
    )
      .map(([key, value]) => `<option value="${key}">${h(value)}</option>`)
      .join(
        "",
      )}</select><small id="edge-type-hint">Контекстная связь соединяет два обычных понятия.</small></label><div class="field-row"><label class="field"><span>Откуда</span><select name="source_card_id">${options}</select></label><label class="field"><span>Куда</span><select name="target_card_id">${options}</select></label></div>${field("Подпись связи", "label", "", { placeholder: "Как связаны эти идеи?" })}<div class="subtle-note">${icon("info")}<p>Текстовые ссылки в конспектах и линии на карте создаются независимо.</p></div>`,
    onSubmit: async (data) => {
      await mapCommand("edge", {
        kind: data.get("kind"),
        source_card_id: data.get("source_card_id"),
        target_card_id: data.get("target_card_id"),
        label: data.get("label") || null,
      });
      toast("Связь создана");
    },
  });
  $("[name=target_card_id]", dialog).selectedIndex = Math.min(
    1,
    cards.length - 1,
  );
  const activeCard = cardFor(state.active);
  if (activeCard) $("[name=source_card_id]", dialog).value = activeCard.id;
  $("[name=kind]", dialog).addEventListener("change", (e) => {
    $("#edge-type-hint", dialog).textContent = {
      contextual: "Контекстная связь соединяет два обычных понятия.",
      hierarchical:
        "Родительское понятие → дочернее понятие. Несколько родителей и циклы разрешены.",
      mention: "Внешнее понятие и обычное понятие курса.",
      exampleAttachment: "Пример и обычное понятие курса.",
      taskAttachment: "Задача и обычное понятие курса.",
    }[e.target.value];
  });
}
function settingsDialog() {
  const settings = state.snapshot.course.settings?.map || {},
    hidden = new Set(settings.hiddenNoteKinds || []),
    dialog = modal({
      title: "Карта в вашем стиле",
      description:
        "Настройки сохраняются вместе с курсом. Скрытые объекты остаются в конспектах.",
      wide: true,
      submit: "Применить",
      body: `<h3 class="settings-section-title">Видимость и карточки</h3><div class="style-row style-table-labels"><span>Показывать тип</span><span>Заливка</span><span>Контур</span><span>Форма</span></div>${Object.entries(
        kinds,
      )
        .map(([kind, label]) => {
          const style = {
            ...cardPalette[kind],
            ...settings.cardStyles?.[kind],
          };
          return `<div class="style-row"><label><input type="checkbox" name="visible-${kind}" ${hidden.has(kind) ? "" : "checked"}>${h(label)}</label>${kind === "lecture" ? '<span></span><span></span><span class="muted">Рамка</span>' : `<input type="color" name="fill-${kind}" value="${h(style.fill)}" aria-label="Заливка: ${h(label)}"><input type="color" name="border-${kind}" value="${h(style.border)}" aria-label="Контур: ${h(label)}"><select name="shape-${kind}" aria-label="Форма: ${h(label)}"><option value="rounded" ${style.shape === "rounded" ? "selected" : ""}>Мягкая</option><option value="rectangle" ${style.shape === "rectangle" ? "selected" : ""}>Прямая</option><option value="pill" ${style.shape === "pill" ? "selected" : ""}>Овальная</option></select>`}</div>`;
        })
        .join(
          "",
        )}<h3 class="settings-section-title">Линии связей</h3><div class="style-row edge-style-row style-table-labels"><span>Тип связи</span><span>Цвет</span><span>Толщина</span><span>Линия</span><span>→</span><span>Aa</span></div>${Object.entries(
        edgeKinds,
      )
        .map(([kind, label]) => {
          const s = { ...linePalette[kind], ...settings.edgeStyles?.[kind] };
          return `<div class="style-row edge-style-row"><span>${h(label)}</span><input type="color" name="stroke-${kind}" value="${h(s.stroke)}" aria-label="Цвет: ${h(label)}"><input type="number" min="1" max="8" step=".1" name="width-${kind}" value="${s.width}" aria-label="Толщина: ${h(label)}"><select name="dash-${kind}" aria-label="Штриховка: ${h(label)}"><option value="solid" ${s.dash === "solid" ? "selected" : ""}>Сплошная</option><option value="dashed" ${s.dash === "dashed" ? "selected" : ""}>Штрих</option><option value="dotted" ${s.dash === "dotted" ? "selected" : ""}>Точки</option></select><input type="checkbox" name="arrow-${kind}" ${s.arrow ? "checked" : ""} title="Стрелка" aria-label="Стрелка: ${h(label)}"><input type="checkbox" name="label-${kind}" ${s.label ? "checked" : ""} title="Подпись" aria-label="Подпись: ${h(label)}"></div>`;
        })
        .join("")}`,
      onSubmit: async (data) => {
        const cardStyles = {},
          edgeStyles = {},
          hiddenNoteKinds = [];
        for (const kind of Object.keys(kinds)) {
          if (!data.has("visible-" + kind)) hiddenNoteKinds.push(kind);
          if (kind !== "lecture")
            cardStyles[kind] = {
              ...cardPalette[kind],
              ...settings.cardStyles?.[kind],
              fill: data.get("fill-" + kind),
              border: data.get("border-" + kind),
              shape: data.get("shape-" + kind),
            };
        }
        for (const kind of Object.keys(edgeKinds))
          edgeStyles[kind] = {
            stroke: data.get("stroke-" + kind),
            width: Number(data.get("width-" + kind)),
            dash: data.get("dash-" + kind),
            arrow: data.has("arrow-" + kind),
            label: data.has("label-" + kind),
          };
        await mapCommand("settings", {
          hiddenNoteKinds,
          cardStyles,
          edgeStyles,
        });
        toast("Оформление карты сохранено");
      },
    });
}

function hideSelection() {
  state.selection = null;
  $("#selection-toolbar").classList.add("hidden");
}
function captureSelection() {
  const reader = $("#note-reader"),
    selection = window.getSelection();
  if (
    !reader ||
    !selection ||
    selection.isCollapsed ||
    !selection.toString().trim()
  ) {
    hideSelection();
    return;
  }
  if (
    !reader.contains(selection.anchorNode) ||
    !reader.contains(selection.focusNode)
  )
    return;
  const tab = activeTab();
  if (dirty(tab)) {
    toast(
      "Сначала сохраните черновик, чтобы добавить ссылку к его тексту.",
      "error",
    );
    hideSelection();
    return;
  }
  try {
    state.selection = {
      note_id: state.active,
      revision: tab.revision,
      ...getSourceSelection(reader),
    };
    const rect = selection.getRangeAt(0).getBoundingClientRect(),
      toolbar = $("#selection-toolbar");
    toolbar.classList.remove("hidden");
    const width = toolbar.offsetWidth;
    toolbar.style.left =
      Math.min(
        Math.max(8, rect.left + rect.width / 2 - width / 2),
        innerWidth - width - 8,
      ) + "px";
    toolbar.style.top = Math.max(8, rect.top - toolbar.offsetHeight - 9) + "px";
  } catch (error) {
    hideSelection();
    toast(errorMessage(error), "error");
  }
}
async function syncSelectionOwner(noteId) {
  await refresh();
  const note = noteById(noteId),
    tab = tabById(noteId);
  if (tab && note) {
    tab.text = note.markdown;
    tab.savedText = note.markdown;
    tab.revision = note.revision;
  }
  hideSelection();
  window.getSelection()?.removeAllRanges();
  renderEditor();
  persistDrafts();
}
function selectionAction(kind) {
  const selection = state.selection;
  if (!selection) return;
  $("#selection-toolbar").classList.add("hidden");
  if (kind === "create-note") {
    noteForm({ selection });
    return;
  }
  if (kind === "link") {
    const options = state.snapshot.notes;
    const dialog = modal({
      title: "Ссылка на конспект",
      description:
        "Выберите конспект текущего курса. Он может быть без карточки.",
      submit: "Добавить ссылку",
      body: `<div class="selection-quote">${h(selection.selected_text)}</div><label class="search-field">${icon("search")}<input type="search" data-picker-search placeholder="Найти конспект…" aria-label="Найти цель ссылки"></label><div class="note-picker">${options.map((note) => `<label class="note-picker-option" data-picker-title="${h(note.title.toLocaleLowerCase())}"><input type="radio" name="target_note_id" value="${h(note.id)}" required><span class="note-kind-icon ${note.kind}">${icon(note.kind)}</span><span><strong>${h(note.title)}</strong><small>${h(kinds[note.kind])}${!cardFor(note.id) && !boxFor(note.id) ? " · Без карточки" : ""}</small></span></label>`).join("")}</div>`,
      onSubmit: async (data) => {
        await api(`${base}/selection/link`, {
          ...selection,
          target_note_id: data.get("target_note_id"),
        });
        await syncSelectionOwner(selection.note_id);
        toast("Ссылка добавлена");
      },
    });
    $("[data-picker-search]", dialog).addEventListener("input", (e) =>
      $$("[data-picker-title]", dialog).forEach((el) =>
        el.classList.toggle(
          "hidden",
          !el.dataset.pickerTitle.includes(e.target.value.toLocaleLowerCase()),
        ),
      ),
    );
    return;
  }
  if (kind === "fact") {
    const unbound = state.snapshot.facts.filter(
      (f) =>
        f.owner_note_id === selection.note_id &&
        !noteById(selection.note_id).markdown.includes(
          `synopsis://fact/${f.id}`,
        ),
    );
    const dialog = modal({
      title: "Факт к фрагменту",
      description:
        "Комментарий скрыт в чтении и раскрывается по нажатию на текст.",
      submit: "Добавить факт",
      body: `<div class="selection-quote">${h(selection.selected_text)}</div>${unbound.length ? `<label class="field"><span>Комментарий</span><select name="fact_id"><option value="">Создать новый</option>${unbound.map((f) => `<option value="${h(f.id)}">Вернуть: ${h(f.markdown.slice(0, 80) || "Пустой факт")}</option>`).join("")}</select></label>` : ""}<div data-new-fact>${field("Текст факта · Markdown", "markdown", "", { textarea: true, rows: 5, placeholder: "Пояснение, замечание или ваша ассоциация…" })}</div>`,
      onSubmit: async (data) => {
        const factId = data.get("fact_id");
        if (factId)
          await api(`${base}/selection/attach-fact`, {
            ...selection,
            fact_id: factId,
          });
        else {
          if (!data.get("markdown").trim())
            throw new Error("Добавьте текст комментария.");
          await api(`${base}/selection/fact`, {
            ...selection,
            markdown: data.get("markdown"),
          });
        }
        await syncSelectionOwner(selection.note_id);
        toast("Факт прикреплён к тексту");
      },
    });
    $("[name=fact_id]", dialog)?.addEventListener("change", (e) =>
      $("[data-new-fact]", dialog).classList.toggle("hidden", !!e.target.value),
    );
    return;
  }
  if (kind === "source") {
    if (!state.snapshot.sources.length) {
      toast("Сначала добавьте PDF во вкладке «Источники».", "error");
      return;
    }
    modal({
      title: "Ссылка на источник",
      description: "Номер относится к странице PDF-файла, начиная с 1.",
      submit: "Добавить ссылку",
      body: `<div class="selection-quote">${h(selection.selected_text)}</div><label class="field"><span>PDF-источник</span><select name="source_id">${state.snapshot.sources.map((source) => `<option value="${h(source.id)}">${h(source.title)}</option>`).join("")}</select></label>${field("Страница PDF", "page", "", { type: "number", min: 1, placeholder: "Необязательно", hint: "Оставьте поле пустым для ссылки на весь файл." })}`,
      onSubmit: async (data) => {
        await api(`${base}/selection/source`, {
          ...selection,
          source_id: data.get("source_id"),
          page: data.get("page") ? Number(data.get("page")) : null,
        });
        await syncSelectionOwner(selection.note_id);
        toast("Ссылка на источник добавлена");
      },
    });
  }
}
function showFact(id) {
  const fact = state.snapshot.facts.find(
    (f) => f.id === id && f.owner_note_id === state.active,
  );
  if (!fact) {
    toast("Факт не найден в этом конспекте.", "error");
    return;
  }
  const dialog = modal({
    title: "Факт к конспекту",
    description: noteById(fact.owner_note_id)?.title || "",
    submit: null,
    body:
      '<div class="fact-view" data-fact-content></div><button type="button" class="button secondary" data-edit-fact>' +
      icon("edit") +
      "Редактировать факт</button>",
  });
  renderMarkdown($("[data-fact-content]", dialog), fact.markdown, {
    courseId,
    noteId: fact.owner_note_id,
    snapshot: state.snapshot,
    onNote: openNote,
    onFact: showFact,
    onSource: openSource,
  });
  $("[data-edit-fact]", dialog).addEventListener("click", () => {
    dialog.close();
    editFact(id);
  });
}
function editFact(id) {
  const fact = state.snapshot.facts.find((f) => f.id === id);
  if (!fact) return;
  modal({
    title: "Редактировать факт",
    description: "Комментарий остаётся частью этого конспекта.",
    body: field("Текст · Markdown", "markdown", fact.markdown, {
      textarea: true,
      rows: 7,
    }),
    onSubmit: async (data) => {
      await api(`${base}/facts/${fact.id}/save`, {
        owner_note_id: fact.owner_note_id,
        markdown: data.get("markdown"),
      });
      await refresh({ editor: true });
      $("#facts-details")?.setAttribute("open", "");
      toast("Факт сохранён");
    },
  });
}

function renderSources() {
  $("#sources-list").innerHTML = state.snapshot.sources.length
    ? state.snapshot.sources
        .map(
          (source) =>
            `<div class="source-row">${icon("file")}<div><strong>${h(source.title)}</strong><small>PDF${source.page_count ? " · " + source.page_count + " стр." : ""}</small><div class="source-actions"><button data-source-open="${h(source.id)}">Открыть ↗</button><button data-source-rename="${h(source.id)}">Название</button><button data-source-attach="${h(source.id)}">К лекции</button></div></div></div>`,
        )
        .join("")
    : `<div class="empty-state">${icon("paperclip")}<strong>Материалы под рукой</strong>Добавьте PDF с лекцией или презентацией. На него можно ссылаться прямо из текста.</div>`;
  $$("[data-source-open]").forEach((el) =>
    el.addEventListener("click", () => openSource(el.dataset.sourceOpen)),
  );
  $$("[data-source-rename]").forEach((el) =>
    el.addEventListener("click", () => renameSource(el.dataset.sourceRename)),
  );
  $$("[data-source-attach]").forEach((el) =>
    el.addEventListener("click", () =>
      attachSourceDialog(null, el.dataset.sourceAttach),
    ),
  );
}
async function openSource(id, page = null) {
  const target = window.open("about:blank", "_blank");
  if (target) target.opener = null;
  try {
    const result = await api(
      `${base}/sources/${encodeURIComponent(id)}/open${page ? "?page=" + page : ""}`,
    );
    if (target) target.location.href = result.url;
    else {
      const dialog = modal({
        title: "Открыть источник",
        description: page
          ? "Страница PDF: " + page
          : "Браузер не открыл новую вкладку автоматически.",
        submit: null,
        body: `<a class="button primary" href="${h(result.url)}" target="_blank" rel="noopener noreferrer">${icon("external")}Открыть PDF${page ? " · стр. " + page : ""}</a>`,
      });
    }
    if (page) toast("Открываем PDF · страница " + page);
  } catch (error) {
    target?.close();
    report(error);
  }
}
function renameSource(id) {
  const source = state.snapshot.sources.find((s) => s.id === id);
  modal({
    title: "Название источника",
    description: "Ссылки на PDF останутся рабочими.",
    body: field("Название", "title", source.title, { required: true }),
    onSubmit: async (data) => {
      await api(`${base}/sources/${id}/rename`, {
        title: data.get("title").trim(),
      });
      await refresh({ editor: true });
      toast("Источник переименован");
    },
  });
}
function attachSourceDialog(lectureId = null, sourceId = null) {
  const lectures = state.snapshot.notes.filter((n) => n.kind === "lecture");
  if (!lectures.length) {
    toast("Сначала создайте лекцию.", "error");
    return;
  }
  if (!state.snapshot.sources.length) {
    state.uploadLectureId = lectureId;
    $("#source-input").click();
    return;
  }
  modal({
    title: "Источник лекции",
    description:
      "PDF откроется отдельно. Его ссылка появится в конспекте лекции.",
    body: `<label class="field"><span>Источник</span><select name="source_id">${state.snapshot.sources.map((s) => `<option value="${h(s.id)}" ${sourceId === s.id ? "selected" : ""}>${h(s.title)}</option>`).join("")}</select></label><label class="field"><span>Лекция</span><select name="lecture_note_id">${lectures.map((n) => `<option value="${h(n.id)}" ${lectureId === n.id ? "selected" : ""}>${h(n.title)}</option>`).join("")}</select></label>${field("Начальная страница PDF", "page", "", { type: "number", min: 1, placeholder: "Необязательно" })}`,
    onSubmit: async (data) => {
      await api(`${base}/sources/${data.get("source_id")}/attach`, {
        lecture_note_id: data.get("lecture_note_id"),
        page: data.get("page") ? Number(data.get("page")) : null,
      });
      await refresh({ editor: true });
      toast("PDF прикреплён к лекции");
    },
  });
}
async function exportCourse() {
  const doExport = async (save) => {
    if (save)
      for (const tab of state.tabs.filter(dirty))
        while (dirty(tab)) await saveTab(tab.id);
    const response = await fetch(`${base}/export`, { method: "POST" });
    if (!response.ok) {
      let data;
      try {
        data = await response.json();
      } catch {}
      throw new Error(data?.error || "Не удалось экспортировать курс");
    }
    const blob = await response.blob(),
      url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download =
      state.snapshot.course.title.replace(/[<>:"/\\|?*]/g, "_") + ".synopsis";
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    toast("Курс экспортирован вместе с вложениями");
  };
  if (state.tabs.some(dirty)) {
    modal({
      title: "Что включить в экспорт?",
      description: "В открытых вкладках есть несохранённые черновики.",
      submit: "Экспортировать",
      body: '<label class="checkbox-label"><input type="radio" name="export" value="save" checked>Сохранить все черновики и экспортировать</label><label class="checkbox-label"><input type="radio" name="export" value="saved">Экспортировать последнюю сохранённую версию</label>',
      onSubmit: (data) => doExport(data.get("export") === "save"),
    });
  } else {
    try {
      await doExport(false);
    } catch (error) {
      report(error);
    }
  }
}

$("#rename-course").addEventListener("click", () => {
  if (!state.snapshot) return;
  modal({
    title: "Название курса",
    body: field("Название", "title", state.snapshot.course.title, {
      required: true,
      maxlength: 180,
    }),
    onSubmit: async (data) => {
      await api(`${base}/rename`, { title: data.get("title").trim() });
      await refresh();
      toast("Курс переименован");
    },
  });
});
for (const selector of [
  "#new-note",
  "#catalog-add",
  "#map-first-note",
  "#editor-first-note",
])
  $(selector).addEventListener("click", () => {
    if (state.snapshot) noteForm();
  });
$("#new-edge").addEventListener("click", () => {
  if (state.snapshot) edgeForm();
});
$("#map-settings").addEventListener("click", () => {
  if (state.snapshot) settingsDialog();
});
$("#export-course").addEventListener("click", () => {
  if (state.snapshot) exportCourse();
});
for (const selector of [
  "#note-search",
  "#note-kind-filter",
  "#cardless-filter",
])
  $(selector).addEventListener(
    selector === "#note-search" ? "input" : "change",
    () => {
      if (state.snapshot) renderCatalog();
    },
  );
$$("[data-catalog]").forEach((button) =>
  button.addEventListener("click", () => {
    state.catalog = button.dataset.catalog;
    $$("[data-catalog]").forEach((el) =>
      el.classList.toggle("active", el === button),
    );
    $("#notes-catalog").classList.toggle("hidden", state.catalog !== "notes");
    $("#sources-catalog").classList.toggle(
      "hidden",
      state.catalog !== "sources",
    );
  }),
);
$("#toggle-sidebar").addEventListener("click", () =>
  document.body.classList.toggle("sidebar-collapsed"),
);
$("#selection-toolbar").addEventListener("mousedown", (e) =>
  e.preventDefault(),
);
$$("[data-selection]").forEach((button) =>
  button.addEventListener("click", () =>
    selectionAction(button.dataset.selection),
  ),
);
document.addEventListener("mousedown", (e) => {
  if (!e.target.closest("#selection-toolbar,dialog,#note-reader"))
    hideSelection();
});
$("#upload-source").addEventListener("click", () => {
  state.uploadLectureId = null;
  $("#source-input").click();
});
$("#source-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    toast("Добавляем PDF в курс…");
    const result = await upload(
      `${base}/sources${state.uploadLectureId ? "?lecture_note_id=" + encodeURIComponent(state.uploadLectureId) : ""}`,
      file,
    );
    await refresh({ editor: true });
    toast("PDF добавлен в источники");
  } catch (error) {
    report(error);
  } finally {
    e.target.value = "";
    state.uploadLectureId = null;
  }
});
$("#image-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const noteId = state.active;
  try {
    const asset = await upload(`${base}/assets`, file),
      markup = `![${file.name.replace(/[\[\]]/g, "")}](synopsis://asset/${asset.id})`;
    if (state.active === noteId && state.editor) {
      state.editor.insert(markup);
      state.editor.focus();
    } else {
      const tab = tabById(noteId);
      if (tab) {
        tab.text += "\n" + markup;
        schedulePersist();
        refreshChrome();
      }
    }
    toast("Изображение добавлено. Сохраните конспект.");
  } catch (error) {
    report(error);
  } finally {
    e.target.value = "";
  }
});
const splitter = $("#panel-splitter"),
  workspace = $("#workspace");
let resizing = false;
function setPanelWidth(value) {
  const percent = Math.max(25, Math.min(75, value));
  workspace.style.setProperty("--map-width", percent + "%");
  splitter.setAttribute("aria-valuenow", Math.round(percent));
  try {
    localStorage.setItem("synopsis.panel-width", String(percent));
  } catch {}
}
try {
  const width = Number(localStorage.getItem("synopsis.panel-width"));
  if (width >= 25 && width <= 75) setPanelWidth(width);
} catch {}
splitter.addEventListener("pointerdown", (e) => {
  resizing = true;
  splitter.classList.add("dragging");
  splitter.setPointerCapture(e.pointerId);
  e.preventDefault();
});
splitter.addEventListener("pointermove", (e) => {
  if (!resizing) return;
  const rect = workspace.getBoundingClientRect();
  setPanelWidth(((e.clientX - rect.left) / rect.width) * 100);
});
splitter.addEventListener("pointerup", () => {
  resizing = false;
  splitter.classList.remove("dragging");
});
splitter.addEventListener("keydown", (e) => {
  if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    e.preventDefault();
    setPanelWidth(
      Number(splitter.getAttribute("aria-valuenow")) +
        (e.key === "ArrowLeft" ? -3 : 3),
    );
  }
});
window.addEventListener("beforeunload", (e) => {
  persistDrafts();
  if (state.tabs.some(dirty)) {
    e.preventDefault();
    e.returnValue = "";
  }
});
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    if (state.active) saveTab().catch(report);
  }
  if (
    e.key === "/" &&
    !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName) &&
    !document.activeElement.isContentEditable &&
    !document.querySelector("dialog[open]")
  ) {
    e.preventDefault();
    $("#note-search").focus();
  }
  if (e.key === "Escape") hideSelection();
});
async function boot() {
  try {
    await refresh();
    restoreDrafts();
    refreshChrome();
    renderEditor();
    document.documentElement.dataset.synopsisReady = "true";
    $$("[data-startup-control]").forEach((button) => {
      button.disabled = false;
    });
  } catch (error) {
    document.documentElement.dataset.synopsisReady = "error";
    const el = $("#course-error");
    el.classList.remove("hidden");
    el.innerHTML = `${h(errorMessage(error))} <button class="text-button" id="retry-course">Попробовать снова</button> <a class="text-button" href="/">Все курсы</a>`;
    $("#retry-course").addEventListener("click", () => {
      el.classList.add("hidden");
      boot();
    });
  }
}
boot();
