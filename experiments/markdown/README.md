# S00-A: source-mapped Markdown selection spike

**Status: feasibility evidence only; not production-ready.** This is a dependency-free Python 3.14 harness because the repository has no application or installed JavaScript runtime. It deliberately does not claim CommonMark/GFM conformance or browser DOM integration.

## Reproduce

From the repository root:

```powershell
python experiments/markdown/spike.py
```

Actual result on the S00 workspace:

```text
PASS 11/11: source-mapped selection patches and refusals verified
```

Fixtures are in `fixtures.json`; the executable implementation is `spike.py`. It uses a rendered-text run plus an explicit per-character source map, then applies one source-range replacement. The selected run/offset is the stand-in for a DOM Range. It never searches the raw document with `indexOf`/first-match replacement.

## Evidence

| Case | Result |
| --- | --- |
| Repeated phrase | Passed: the fixture selects the second occurrence in one rendered run and only it becomes a link. |
| Cyrillic and emoji | Passed: `Вектор 🚀` maps and patches as one selected label. |
| Partial strong text | Passed: `**важное понятие**` becomes `**[важное](...) понятие**`; delimiters remain untouched. |
| Escaped brackets | Passed: visible `[ и ]` maps to raw `\\[ и \\]`; the exact escapes remain in the new label. |
| GFM-table cell | Passed: a single cell's text is patched; table separators and neighboring cells are byte-identical. |
| Text next to inline formula | Passed: text after `$x^2$` patches without changing formula markup. |
| Existing Markdown link | Refused without a patch (nested link would be invalid). |
| Inline formula | Refused without a patch. |
| Fenced code | Refused without a patch. |
| Display formula / block boundary | Refused without a patch. |
| Stale displayed revision | Refused without a patch. |

For every successful fixture the harness asserts both prefixes and suffixes outside the calculated raw source range are identical. Each refusal raises before any modified string is returned. This directly covers the S00 scope of AC-17/AC-18 for the modeled selection/patch operation; it does not prove the later UI transaction that creates a Note/Card.

## Limits and next decision (D-03 input)

Supported by this spike: nonempty selections contained in one ordinary text run or one table cell, including partial emphasis and escaped punctuation. Selections must not cross runs, lines, block boundaries, or Markdown constructs.

Intentionally refused: existing links, inline/display math, inline/fenced code, empty/unmapped ranges, and stale revisions. Images, raw HTML, task lists, nested link labels, entities, multiline paragraphs, selections spanning emphasis boundaries, and full CommonMark/GFM parsing are **not demonstrated**. The toy renderer only recognizes enough syntax to make these fixtures meaningful; it does not render LaTeX or validate arbitrary formula commands.

Production work needs a maintained CommonMark+GFM renderer with source-position support and browser Range-to-source mapping. It must retain the same refusal-first behavior for unsupported ranges, map UTF-16 DOM offsets carefully (this Python harness indexes Unicode code points), validate link target/course ownership, and perform the final mutation as a revision-checked domain transaction. This spike makes no library selection, no license claim, and no production-readiness claim.
