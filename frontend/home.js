import {
  $,
  escapeHTML as h,
  icon,
  api,
  modal,
  field,
  toast,
  errorMessage,
  upload,
} from "./common.js";

document.documentElement.dataset.synopsisReady = "true";

const grid = $("#course-grid");
async function loadCourses() {
  try {
    const courses = await api("/api/courses");
    $("#course-count").textContent = courses.length;
    $("#sidebar-count").textContent = courses.length;
    grid.innerHTML = courses
      .map(
        (course, i) =>
          `<a class="course-tile tone-${i % 4}" href="/courses/${encodeURIComponent(course.id)}"><div class="tile-top"><span class="tile-icon">${icon("book")}</span><span class="tile-arrow">${icon("arrowRight")}</span></div><div class="tile-title"><span class="eyebrow">УЧЕБНЫЙ КУРС</span><h3>${h(course.title)}</h3></div><div class="tile-footer"><span>${course.note_count != null ? `${course.note_count} конспектов` : "Личное пространство знаний"}</span><span class="tile-status"><i></i>Локально</span></div></a>`,
      )
      .join("");
    const add = document.createElement("button");
    add.className = `new-course-tile ${courses.length ? "" : "first-course-tile"}`;
    add.innerHTML = `<span class="new-tile-icon">${icon("plus")}</span><strong>${courses.length ? "Создать новый курс" : "Ваш первый курс"}</strong><span>${courses.length ? "Ещё одна область для открытий" : "Дайте название тому, что изучаете.\nВсё остальное сложится постепенно."}</span>`;
    add.addEventListener("click", createCourse);
    grid.append(add);
  } catch (error) {
    $("#home-error").innerHTML =
      `${h(errorMessage(error))} <button class="text-button" id="retry-courses">Попробовать снова</button>`;
    $("#home-error").classList.remove("hidden");
    grid.innerHTML = "";
    $("#retry-courses").addEventListener("click", () => {
      $("#home-error").classList.add("hidden");
      loadCourses();
    });
  }
}
function createCourse() {
  modal({
    title: "Начнём с названия",
    description: "Курс объединяет лекции, конспекты и связи между идеями.",
    submit: "Создать курс",
    body: `<div class="modal-symbol">${icon("book")}</div>${field("Название курса", "title", "", { required: true, maxlength: 180, placeholder: "Например, линейная алгебра" })}<div class="subtle-note">${icon("info")}<p>Содержимое хранится на вашем компьютере. Название можно изменить в любой момент.</p></div>`,
    onSubmit: async (data) => {
      const course = await api("/api/courses", {
        title: data.get("title").trim(),
      });
      location.href = `/courses/${encodeURIComponent(course.id)}`;
    },
  });
}
$("#create-course").addEventListener("click", createCourse);
for (const id of ["#import-course", "#sidebar-import"])
  $(id).addEventListener("click", () => $("#import-input").click());
$("#import-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    toast("Открываем файл курса…");
    const course = await upload("/api/import", file);
    location.href = `/courses/${encodeURIComponent(course.id)}`;
  } catch (error) {
    toast(errorMessage(error), "error");
  } finally {
    e.target.value = "";
  }
});
loadCourses();
