import {
  $,
  escapeHTML as h,
  icon,
  kinds,
  edgeKinds,
  modal,
  field,
  confirmAction,
  report,
  toast,
} from "./common.js";

export const cardPalette = {
  concept: {
    fill: "#f8f5fd",
    border: "#cab9df",
    text: "#725984",
    shape: "rounded",
  },
  externalConcept: {
    fill: "#f1f6fa",
    border: "#b7c8d8",
    text: "#647e98",
    shape: "rounded",
  },
  example: {
    fill: "#f5f7eb",
    border: "#c4cdaa",
    text: "#809068",
    shape: "rounded",
  },
  task: {
    fill: "#fff6ed",
    border: "#dec5ab",
    text: "#b18c68",
    shape: "rounded",
  },
};
export const linePalette = {
  contextual: {
    stroke: "#b29ac6",
    width: 1.7,
    dash: "solid",
    arrow: true,
    label: true,
  },
  hierarchical: {
    stroke: "#a796bd",
    width: 1.7,
    dash: "solid",
    arrow: true,
    label: true,
  },
  mention: {
    stroke: "#a3b5c6",
    width: 1.5,
    dash: "dashed",
    arrow: true,
    label: true,
  },
  exampleAttachment: {
    stroke: "#b3be94",
    width: 1.5,
    dash: "dashed",
    arrow: true,
    label: true,
  },
  taskAttachment: {
    stroke: "#d1b496",
    width: 1.5,
    dash: "dashed",
    arrow: true,
    label: true,
  },
};
const svgNS = "http://www.w3.org/2000/svg";
const center = (c) => ({
  x: c.position.x + c.size.x / 2,
  y: c.position.y + c.size.y / 2,
});
const toWorld = (s, t, p) => ({
  x: s.x + p.u * (t.x - s.x) - p.v * (t.y - s.y),
  y: s.y + p.u * (t.y - s.y) + p.v * (t.x - s.x),
});
const toRelative = (s, t, p) => {
  const dx = t.x - s.x,
    dy = t.y - s.y,
    l = dx * dx + dy * dy;
  return {
    u: ((p.x - s.x) * dx + (p.y - s.y) * dy) / l,
    v: ((p.x - s.x) * -dy + (p.y - s.y) * dx) / l,
  };
};
const truncate = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
function wrap(text, maxChars, maxLines) {
  const words = String(text || "").split(/\s+/),
    lines = [];
  let line = "";
  for (const word of words) {
    if ((line + " " + word).trim().length > maxChars && line) {
      lines.push(line);
      line = word;
    } else line = (line + " " + word).trim();
  }
  if (line) lines.push(line);
  return lines
    .slice(0, maxLines)
    .map((line, i) =>
      i === maxLines - 1 && lines.length > maxLines
        ? truncate(line, maxChars - 1) + "…"
        : truncate(line, maxChars),
    );
}

export class CourseMap {
  constructor({ svg, onOpen, onCommand, onEditEdge }) {
    this.svg = svg;
    this.onOpen = onOpen;
    this.onCommand = onCommand;
    this.onEditEdge = onEditEdge;
    this.snapshot = null;
    this.view = { x: 45, y: 155, scale: 1 };
    this.selectedNote = null;
    this.selectedEdge = null;
    this.drag = null;
    this.fitOnce = false;
    svg.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        this.zoom(e.deltaY < 0 ? 1.1 : 1 / 1.1, e.clientX, e.clientY);
      },
      { passive: false },
    );
    svg.addEventListener("pointerdown", (e) => this.pointerDown(e));
    svg.addEventListener("pointermove", (e) => this.pointerMove(e));
    svg.addEventListener("pointerup", (e) => this.pointerUp(e));
    svg.addEventListener("pointercancel", () => {
      if (this.drag?.type === "pan") {
        this.drag = null;
        return;
      }
      this.drag = null;
      this.onCommand(null).catch(report);
    });
    svg.addEventListener("dblclick", (e) => {
      const edge = e.target.closest("[data-edge]");
      if (edge) {
        e.preventDefault();
        this.addControl(edge.dataset.edge, this.world(e.clientX, e.clientY));
      }
    });
    svg.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        this.selectedEdge = null;
        this.render();
      }
      if ((e.key === "Delete" || e.key === "Backspace") && this.selectedEdge) {
        e.preventDefault();
        this.removeEdge();
      }
      if (e.key === "0") {
        this.fit();
      }
      if (e.key === "+") this.zoom(1.15);
      if (e.key === "-") this.zoom(1 / 1.15);
    });
    $("#zoom-in").addEventListener("click", () => this.zoom(1.2));
    $("#zoom-out").addEventListener("click", () => this.zoom(1 / 1.2));
    $("#zoom-fit").addEventListener("click", () => this.fit());
    this.resizeObserver = new ResizeObserver(() => {
      const size = { width: svg.clientWidth, height: svg.clientHeight };
      if (this.snapshot && !this.fitOnce) {
        this.fitOnce = true;
        this.fit();
      } else if (this.viewportSize && size.width && size.height) {
        this.view.x += (size.width - this.viewportSize.width) / 2;
        this.view.y += (size.height - this.viewportSize.height) / 2;
        this.transform();
      }
      this.viewportSize = size;
    });
    this.resizeObserver.observe(svg);
  }
  update(snapshot, selectedNote) {
    this.snapshot = snapshot;
    this.selectedNote = selectedNote;
    if (
      this.selectedEdge &&
      !snapshot.edges.some((e) => e.id === this.selectedEdge)
    )
      this.selectedEdge = null;
    this.render();
    if (!this.fitOnce && this.svg.clientWidth) {
      this.fitOnce = true;
      this.fit();
    }
  }
  world(clientX, clientY) {
    const r = this.svg.getBoundingClientRect();
    return {
      x: (clientX - r.left - this.view.x) / this.view.scale,
      y: (clientY - r.top - this.view.y) / this.view.scale,
    };
  }
  zoom(factor, clientX, clientY) {
    const r = this.svg.getBoundingClientRect(),
      x = clientX ?? r.left + r.width / 2,
      y = clientY ?? r.top + r.height / 2,
      p = this.world(x, y),
      scale = Math.min(2.8, Math.max(0.16, this.view.scale * factor));
    this.view = {
      scale,
      x: x - r.left - p.x * scale,
      y: y - r.top - p.y * scale,
    };
    this.transform();
  }
  transform() {
    const g = $("[data-world]", this.svg);
    if (g)
      g.setAttribute(
        "transform",
        `translate(${this.view.x} ${this.view.y}) scale(${this.view.scale})`,
      );
    $("#zoom-value").textContent = Math.round(this.view.scale * 100) + "%";
  }
  fit() {
    if (!this.snapshot) return;
    const items = [
      { position: { x: 20, y: -130 }, size: { x: 250, y: 75 } },
      ...this.snapshot.cards,
      ...this.snapshot.lecture_boxes,
    ];
    const x0 = Math.min(...items.map((c) => c.position.x)) - 45,
      y0 = Math.min(...items.map((c) => c.position.y)) - 45,
      x1 = Math.max(...items.map((c) => c.position.x + c.size.x)) + 45,
      y1 = Math.max(...items.map((c) => c.position.y + c.size.y)) + 55,
      w = this.svg.clientWidth,
      height = this.svg.clientHeight;
    if (!w || !height) return;
    if (!this.snapshot.cards.length && !this.snapshot.lecture_boxes.length) {
      this.view = { scale: 1, x: (w - 250) / 2 - 20, y: 170 };
      this.transform();
      return;
    }
    const scale = Math.min(1.05, w / (x1 - x0), height / (y1 - y0));
    this.view = {
      scale,
      x: (w - (x1 - x0) * scale) / 2 - x0 * scale,
      y: (height - (y1 - y0) * scale) / 2 - y0 * scale,
    };
    this.transform();
  }
  focusNote(noteId) {
    const card =
      this.snapshot.cards.find((c) => c.note_id === noteId) ||
      this.snapshot.lecture_boxes.find((c) => c.note_id === noteId);
    if (!card) return;
    const p = center(card),
      scale = Math.max(0.65, this.view.scale);
    this.view = {
      scale,
      x: this.svg.clientWidth / 2 - p.x * scale,
      y: this.svg.clientHeight / 2 - p.y * scale,
    };
    this.selectedNote = noteId;
    this.render();
  }
  freePosition() {
    const p = this.world(
      this.svg.getBoundingClientRect().left + this.svg.clientWidth / 2,
      this.svg.getBoundingClientRect().top + this.svg.clientHeight / 2,
    );
    return { x: Math.round(p.x - 110), y: Math.round(p.y - 50) };
  }
  edgePoints(edge) {
    const s = this.snapshot.cards.find((c) => c.id === edge.source_card_id),
      t = this.snapshot.cards.find((c) => c.id === edge.target_card_id);
    if (!s || !t) return [];
    const a = center(s),
      b = center(t);
    return [
      a,
      ...(edge.geometry?.control_points || []).map((p) => toWorld(a, b, p)),
      b,
    ];
  }
  clippedPoints(edge, points) {
    const result = points.map((p) => ({ ...p }));
    for (const [index, nextIndex, cardId] of [
      [0, 1, edge.source_card_id],
      [points.length - 1, points.length - 2, edge.target_card_id],
    ]) {
      const card = this.snapshot.cards.find((c) => c.id === cardId),
        p = points[index],
        q = points[nextIndex],
        dx = q.x - p.x,
        dy = q.y - p.y;
      const factor = Math.min(
        dx ? Math.abs(card.size.x / 2 / dx) : Infinity,
        dy ? Math.abs(card.size.y / 2 / dy) : Infinity,
      );
      if (Number.isFinite(factor)) {
        result[index] = { x: p.x + dx * factor, y: p.y + dy * factor };
      }
    }
    return result;
  }
  render() {
    if (!this.snapshot) return;
    const { notes, cards, lecture_boxes: boxes, edges, course } = this.snapshot,
      lookup = new Map(notes.map((n) => [n.id, n])),
      settings = course.settings?.map || {},
      hidden = new Set(settings.hiddenNoteKinds || []),
      visible = cards.filter((c) => !hidden.has(lookup.get(c.note_id)?.kind)),
      visibleIds = new Set(visible.map((c) => c.id));
    let content = "";
    const rootTitle = wrap(course.title, 27, 2);
    content += `<g class="course-root" data-root="true" transform="translate(20 -130)"><rect width="250" height="75" rx="11" fill="#eee7f5" stroke="#d3c3e0"/><rect x="15" y="20" width="33" height="33" rx="8" fill="#dfd0eb"/><text x="31.5" y="43" text-anchor="middle" fill="#aa8cbe" font-family="Georgia,serif" font-style="italic" font-size="28">s</text><text x="60" y="20" font-family="Segoe UI,sans-serif" font-size="7" letter-spacing="1.5" fill="#b09abe">КУРС</text>${rootTitle.map((line, i) => `<text x="60" y="${39 + i * 17}" font-family="Segoe UI,sans-serif" font-size="12" fill="#8f73a0">${h(line)}</text>`).join("")}</g>`;
    for (const box of boxes) {
      const note = lookup.get(box.note_id);
      if (!note || hidden.has("lecture")) continue;
      content += `<g class="map-box" data-box="${h(box.id)}" data-note="${h(note.id)}" transform="translate(${box.position.x} ${box.position.y})"><rect class="box-border" width="${box.size.x}" height="${box.size.y}" rx="13" fill="#f4eef866" stroke="${note.id === this.selectedNote ? "#bba0d0" : "#ddd0e6"}" stroke-width="${note.id === this.selectedNote ? 1.8 : 1.1}"/><path d="M0 42H${box.size.x}" stroke="#e4d8ed"/><text x="17" y="26" font-family="Segoe UI,sans-serif" font-size="11" fill="#a388b5">${h(truncate(note.title, Math.floor((box.size.x - 40) / 6.2)))}</text><path class="box-resize" data-resize="${h(box.id)}" d="M${box.size.x - 14} ${box.size.y - 4}l10-10m-5 10 5-5" stroke="#cbb6da" stroke-width="2"/><rect class="box-resize" data-resize="${h(box.id)}" x="${box.size.x - 20}" y="${box.size.y - 20}" width="20" height="20" fill="transparent"/></g>`;
    }
    for (const edge of edges) {
      if (
        !visibleIds.has(edge.source_card_id) ||
        !visibleIds.has(edge.target_card_id)
      )
        continue;
      const points = this.edgePoints(edge);
      if (points.length < 2) continue;
      const style = {
          ...linePalette[edge.kind],
          ...settings.edgeStyles?.[edge.kind],
        },
        isSelected = this.selectedEdge === edge.id,
        d = this.clippedPoints(edge, points)
          .map((p, i) => (i ? "L" : "M") + p.x + " " + p.y)
          .join(" "),
        dash =
          style.dash === "dashed"
            ? "7 5"
            : style.dash === "dotted"
              ? "2 4"
              : undefined;
      content += `<g class="map-edge" data-edge="${h(edge.id)}"><path d="${d}" fill="none" stroke="transparent" stroke-width="15"/><path d="${d}" fill="none" stroke="${h(style.stroke)}" stroke-width="${Number(style.width) + (isSelected ? 0.8 : 0)}" ${dash ? `stroke-dasharray="${dash}"` : ""} ${style.arrow ? 'marker-end="url(#arrow-' + h(edge.kind) + ')"' : ""} stroke-linecap="round" stroke-linejoin="round"/>`;
      if (edge.label && style.label !== false) {
        const p = points[Math.floor((points.length - 1) / 2)],
          q = points[Math.ceil((points.length - 1) / 2)],
          x = (p.x + q.x) / 2,
          y = (p.y + q.y) / 2;
        content += `<rect x="${x - Math.min(edge.label.length * 2.8, 95) - 7}" y="${y - 12}" width="${Math.min(edge.label.length * 5.6, 190) + 14}" height="20" rx="5" fill="#fffefa" stroke="#e8ddee"/><text x="${x}" y="${y + 1.5}" text-anchor="middle" fill="${h(style.stroke)}" font-family="Segoe UI,sans-serif" font-size="9">${h(truncate(edge.label, 34))}</text>`;
      }
      content += "</g>";
      if (isSelected) {
        points.slice(1, -1).forEach((p, i) => {
          content += `<circle class="map-control" data-control="${h(edge.id)}" data-index="${i}" cx="${p.x}" cy="${p.y}" r="6" fill="#fffefa" stroke="#ad8fc5" stroke-width="2"/>`;
        });
      }
    }
    for (const card of visible) {
      const note = lookup.get(card.note_id);
      if (!note) continue;
      const style = {
          ...cardPalette[note.kind],
          ...settings.cardStyles?.[note.kind],
          ...card.appearance,
        },
        w = card.size.x,
        height = card.size.y,
        titleLines = wrap(note.title, Math.floor((w - 31) / 6.4), 2),
        summaryLines = wrap(
          note.summary,
          Math.floor((w - 30) / 5.3),
          Math.max(0, Math.floor((height - 28 - titleLines.length * 16) / 13)),
        ),
        radius =
          style.shape === "rectangle"
            ? 2
            : style.shape === "pill"
              ? Math.min(25, height / 3)
              : 10;
      content += `<g class="map-card ${note.id === this.selectedNote ? "selected" : ""}" data-card="${h(card.id)}" data-note="${h(note.id)}" transform="translate(${card.position.x} ${card.position.y})"><rect class="card-border" width="${w}" height="${height}" rx="${radius}" fill="${h(style.fill)}" stroke="${h(style.border)}" stroke-width="1.15"/><circle cx="15" cy="15" r="2.3" fill="${h(style.border)}"/><text x="24" y="18" font-family="Segoe UI,sans-serif" font-size="7" letter-spacing=".6" fill="${h(style.text)}" opacity=".67">${h(kinds[note.kind].toUpperCase())}</text>${titleLines.map((line, i) => `<text x="15" y="${39 + i * 16}" font-family="Segoe UI,sans-serif" font-size="12.5" font-weight="550" fill="${h(style.text)}">${h(line)}</text>`).join("")}${summaryLines.map((line, i) => `<text x="15" y="${43 + titleLines.length * 16 + i * 13}" font-family="Segoe UI,sans-serif" font-size="10" fill="${h(style.text)}" opacity=".65">${h(line)}</text>`).join("")}</g>`;
    }
    const defs = Object.entries(edgeKinds)
      .map(([kind]) => {
        const style = { ...linePalette[kind], ...settings.edgeStyles?.[kind] };
        return `<marker id="arrow-${kind}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M1 1 9 5 1 9" fill="none" stroke="${h(style.stroke)}" stroke-width="1.2"/></marker>`;
      })
      .join("");
    this.svg.innerHTML = `<defs>${defs}</defs><g data-world="true">${content}</g>`;
    this.transform();
    $("#map-count").textContent =
      visible.length + boxes.filter(() => !hidden.has("lecture")).length;
    $("#map-empty").classList.toggle("hidden", cards.length + boxes.length > 0);
    this.renderInspector();
  }
  renderInspector() {
    const panel = $("#edge-inspector"),
      edge = this.snapshot.edges.find((e) => e.id === this.selectedEdge);
    if (!edge) {
      panel.classList.add("hidden");
      return;
    }
    panel.classList.remove("hidden");
    panel.innerHTML = `<div class="edge-inspector-header"><strong>${h(edgeKinds[edge.kind])}</strong><button class="icon-button" data-edge-action="close" aria-label="Закрыть свойства связи">${icon("close")}</button></div><p>${edge.label ? h(edge.label) : "Добавьте подпись, чтобы пояснить связь."}<br>Перемещайте круглые точки для изменения линии.</p><div class="edge-inspector-actions"><button class="button secondary" data-edge-action="label">${icon("edit")}Подпись</button><button class="button secondary" data-edge-action="point">${icon("plus")}Точка</button>${edge.geometry?.control_points?.length ? `<button class="button ghost" data-edge-action="remove-point">Убрать точку</button>` : ""}<button class="icon-button" data-edge-action="delete" aria-label="Удалить связь" title="Удалить связь">${icon("trash")}</button></div>`;
    panel.querySelectorAll("[data-edge-action]").forEach((el) =>
      el.addEventListener("click", () => {
        switch (el.dataset.edgeAction) {
          case "close":
            this.selectedEdge = null;
            this.render();
            break;
          case "label":
            modal({
              title: "Подпись связи",
              description: edgeKinds[edge.kind],
              body: field("Пояснение", "label", edge.label || "", {
                placeholder: "Например, частный случай",
              }),
              onSubmit: async (data) => {
                await this.onCommand("edge-label", {
                  edge_id: edge.id,
                  label: data.get("label"),
                });
                toast("Подпись сохранена");
              },
            });
            break;
          case "point":
            this.addControl(edge.id);
            break;
          case "remove-point":
            this.onCommand("remove-control", {
              edge_id: edge.id,
              index: edge.geometry.control_points.length - 1,
            }).catch(report);
            break;
          case "delete":
            this.removeEdge();
            break;
        }
      }),
    );
  }
  async addControl(edgeId, position) {
    const edge = this.snapshot.edges.find((e) => e.id === edgeId);
    if (!edge) return;
    const points = this.edgePoints(edge),
      a = points[Math.floor((points.length - 1) / 2)],
      b = points[Math.ceil((points.length - 1) / 2)],
      p = position || { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 50 };
    try {
      await this.onCommand("control", {
        edge_id: edgeId,
        index: edge.geometry?.control_points?.length || 0,
        position: p,
      });
      this.selectedEdge = edgeId;
      this.render();
    } catch (error) {
      report(error);
    }
  }
  removeEdge() {
    const id = this.selectedEdge;
    confirmAction(
      "Удалить связь?",
      "Карточки и текстовые ссылки в конспектах сохранятся.",
      "Удалить связь",
      async () => {
        await this.onCommand("remove-edge", { edge_id: id });
        this.selectedEdge = null;
        toast("Связь удалена");
      },
    );
  }
  pointerDown(e) {
    if (e.button !== 0 || !this.snapshot) return;
    const control = e.target.closest("[data-control]"),
      resize = e.target.closest("[data-resize]"),
      card = e.target.closest("[data-card]"),
      box = e.target.closest("[data-box]"),
      edge = e.target.closest("[data-edge]"),
      point = this.world(e.clientX, e.clientY);
    this.svg.setPointerCapture(e.pointerId);
    if (control) {
      const item = this.snapshot.edges.find(
        (x) => x.id === control.dataset.control,
      );
      this.drag = {
        type: "control",
        id: item.id,
        index: Number(control.dataset.index),
        origin: structuredClone(item.geometry.control_points),
        start: point,
      };
    } else if (resize) {
      const item = this.snapshot.lecture_boxes.find(
        (x) => x.id === resize.dataset.resize,
      );
      this.drag = {
        type: "resize",
        id: item.id,
        size: { ...item.size },
        start: point,
      };
    } else if (card) {
      const item = this.snapshot.cards.find((x) => x.id === card.dataset.card);
      this.selectedNote = item.note_id;
      this.selectedEdge = null;
      this.drag = {
        type: "card",
        id: item.id,
        note: item.note_id,
        position: { ...item.position },
        start: point,
      };
    } else if (box) {
      const item = this.snapshot.lecture_boxes.find(
        (x) => x.id === box.dataset.box,
      );
      this.selectedNote = item.note_id;
      this.selectedEdge = null;
      this.drag = {
        type: "box",
        id: item.id,
        note: item.note_id,
        position: { ...item.position },
        children: this.snapshot.cards
          .filter((c) => c.lecture_box_id === item.id)
          .map((c) => ({ id: c.id, position: { ...c.position } })),
        start: point,
      };
    } else if (edge) {
      this.selectedEdge = edge.dataset.edge;
      this.drag = null;
      this.render();
    } else {
      this.selectedEdge = null;
      this.drag = {
        type: "pan",
        client: { x: e.clientX, y: e.clientY },
        view: { ...this.view },
      };
      this.renderInspector();
    }
    this.moved = false;
  }
  pointerMove(e) {
    if (!this.drag) return;
    const drag = this.drag;
    if (drag.type === "pan") {
      const dx = e.clientX - drag.client.x,
        dy = e.clientY - drag.client.y;
      this.view.x = drag.view.x + dx;
      this.view.y = drag.view.y + dy;
      this.moved ||= Math.abs(dx) + Math.abs(dy) > 3;
      this.transform();
      return;
    }
    const point = this.world(e.clientX, e.clientY),
      dx = point.x - drag.start.x,
      dy = point.y - drag.start.y;
    this.moved ||= Math.abs(dx) + Math.abs(dy) > 3;
    if (!this.moved) return;
    if (drag.type === "card") {
      const item = this.snapshot.cards.find((c) => c.id === drag.id);
      item.position = { x: drag.position.x + dx, y: drag.position.y + dy };
    } else if (drag.type === "box") {
      const item = this.snapshot.lecture_boxes.find((c) => c.id === drag.id);
      item.position = { x: drag.position.x + dx, y: drag.position.y + dy };
      for (const child of drag.children)
        this.snapshot.cards.find((c) => c.id === child.id).position = {
          x: child.position.x + dx,
          y: child.position.y + dy,
        };
    } else if (drag.type === "resize") {
      this.snapshot.lecture_boxes.find((c) => c.id === drag.id).size = {
        x: Math.max(280, drag.size.x + dx),
        y: Math.max(160, drag.size.y + dy),
      };
    } else if (drag.type === "control") {
      const edge = this.snapshot.edges.find((c) => c.id === drag.id),
        s = center(
          this.snapshot.cards.find((c) => c.id === edge.source_card_id),
        ),
        t = center(
          this.snapshot.cards.find((c) => c.id === edge.target_card_id),
        );
      edge.geometry.control_points[drag.index] = toRelative(s, t, point);
    }
    this.render();
  }
  async pointerUp(e) {
    const drag = this.drag;
    if (!drag) return;
    this.drag = null;
    try {
      this.svg.releasePointerCapture(e.pointerId);
    } catch {}
    if (!this.moved) {
      if (drag.note) this.onOpen(drag.note);
      return;
    }
    if (drag.type === "pan") return;
    const point = this.world(e.clientX, e.clientY),
      delta = { x: point.x - drag.start.x, y: point.y - drag.start.y };
    try {
      if (drag.type === "card")
        await this.onCommand("move-card", { card_id: drag.id, delta });
      if (drag.type === "box")
        await this.onCommand("move-box", { box_id: drag.id, delta });
      if (drag.type === "resize")
        await this.onCommand("resize-box", {
          box_id: drag.id,
          size: this.snapshot.lecture_boxes.find((c) => c.id === drag.id).size,
        });
      if (drag.type === "control")
        await this.onCommand("control", {
          edge_id: drag.id,
          index: drag.index,
          position: point,
        });
    } catch (error) {
      report(error);
      try {
        await this.onCommand(null);
      } catch {}
    }
  }
}
