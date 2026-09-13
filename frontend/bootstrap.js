/* A small independent guard keeps module failures visible and recoverable. */
(() => {
  let displayed = false;
  function show(message, source = "") {
    if (displayed) return;
    displayed = true;
    const mount = () => {
      const target = document.querySelector("#home-error, #course-error");
      if (!target) return;
      target.classList.remove("hidden");
      target.setAttribute("role", "alert");
      target.textContent =
        message + (source ? ` Не загружен скрипт: ${source}. ` : " ");
      const retry = document.createElement("button");
      retry.className = "text-button";
      retry.textContent = "Перезагрузить страницу";
      retry.addEventListener("click", () => location.reload());
      target.append(retry);
      const diagnostics = document.createElement("a");
      diagnostics.className = "text-button";
      diagnostics.href = "/api/health";
      diagnostics.target = "_blank";
      diagnostics.rel = "noopener noreferrer";
      diagnostics.textContent = "Диагностика сервера";
      target.append(" ", diagnostics);
      fetch("/api/health")
        .then((response) => response.json())
        .then((health) => {
          const details = document.createElement("p");
          if (health.app !== "synopsis") {
            details.textContent =
              "Этот сервер не поддерживает диагностику текущей версии. Проверьте папку запуска и перезапустите сервер.";
          } else if (health.ui?.missing_files?.length) {
            details.textContent = `В каталоге ${health.ui.root} отсутствуют или недоступны: ${health.ui.missing_files.join(", ")}. Восстановите эти файлы и перезапустите сервер.`;
          } else {
            details.textContent = `Сервер отдаёт UI из ${health.ui?.root}. Экземпляр: ${health.instance_id}.`;
          }
          target.append(details);
        })
        .catch(() => {
          /* The original load error remains visible without diagnostics. */
        });
    };
    if (document.readyState === "loading")
      document.addEventListener("DOMContentLoaded", mount, { once: true });
    else mount();
  }
  window.addEventListener(
    "error",
    (event) => {
      if (
        event.target instanceof HTMLScriptElement ||
        event instanceof ErrorEvent
      ) {
        show(
          "Не удалось загрузить часть интерфейса. Ваши сохранённые курсы и черновики остаются на месте.",
          event.target instanceof HTMLScriptElement
            ? new URL(event.target.src).pathname
            : "",
        );
      }
    },
    true,
  );
  setTimeout(() => {
    if (!document.documentElement.dataset.synopsisReady)
      show(
        "Интерфейс загружается дольше обычного. Проверьте, что приложение запущено.",
      );
  }, 12000);
})();
