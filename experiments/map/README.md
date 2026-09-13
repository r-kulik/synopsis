# S00-B: map and geometry feasibility spike

This is an executable data/geometry spike for AC-08, not a production map module or a browser/UI proof. It intentionally uses only Python's standard library because this repository has no installed frontend dependencies and Node.js was not available in the checked environment.

Run from the repository root:

```powershell
python experiments/map/map_spike.py
```

The command runs four assertions over the `fixture()` course. It creates two lecture boxes (`Векторы`, `Матрицы`), ordinary concept cards, an external concept, an example and a task. The fixture includes the labelled cross-lecture contextual edge `Вектор → Матрица`, two manually placed control points, an allowed three-card hierarchy cycle, and compatible mention/example/task edges.

## Geometry rule proved here

Endpoints are derived from the centres of the source and target cards. Each manually dragged control point is serialized as `(u, v)` in the endpoint-relative coordinate frame:

```text
P = S + u * (T - S) + v * perpendicular(T - S)
perpendicular(x, y) = (-y, x)
```

Dragging converts the chosen world coordinate to `(u, v)`. Rendering rebuilds a polyline `S → P1…Pn → T`. Moving a card changes only its endpoint; moving a lecture box translates that box and every member card. Because control points remain endpoint-relative, they reflow deterministically after either endpoint or container movement. The exact `(u, v)` values, label, endpoint IDs and kind are JSON-serialized; the test reloads JSON and compares the reconstructed path exactly.

Visibility is a non-destructive type filter: hidden card types stay in data, and an edge is hidden whenever either endpoint is hidden. Hierarchy validation accepts concept→concept cycles, while rejecting an external concept in hierarchy.

## Candidate library and licensing finding

The documentation's candidate for the production UI is React Flow / `@xyflow/react`, stated there as MIT, with custom SVG edges and grouped nodes suitable for a later UI spike. This Python result does not install, bundle, or prove a particular React Flow version.

The **React Flow Editable Edge** example must not be copied into this project as MIT code: the architecture document identifies it as an example under the separate **xyflow Pro License**. Its control-point interaction is therefore a product/licensing risk until a license is acquired or an independently implemented MIT-compatible interaction is used. This spike's endpoint-relative geometry is an algorithmic data contract, not copied Pro UI code; a production implementation still needs an accessibility, pointer interaction, hit-testing and SVG/browser test.

## Limits

- No React Flow, DOM drag interaction, rendering, browser persistence, import/export archive, or production API is demonstrated.
- A polyline is used only to make the persisted geometry inspectable; a future renderer may turn it into an SVG path without changing the stored `(u, v)` rule.
- Coincident endpoint centres are rejected when adding/editing a manual point; a production UI needs a user-facing recovery path.
