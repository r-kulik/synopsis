"""Dependency-free S00 source-map experiment; not a production Markdown parser."""
import json
from pathlib import Path

class Refusal(Exception): pass

def add_run(raw, lo, hi, context, runs):
    runs.append({"text": raw[lo:hi], "chars": [(i, i + 1) for i in range(lo, hi)], "context": context})

def inline(raw, lo, hi, context, runs):
    text, chars = "", []
    def flush():
        nonlocal text, chars
        if text: runs.append({"text": text, "chars": chars, "context": context})
        text, chars = "", []
    i = lo
    while i < hi:
        if raw[i] == "[":
            close, end = raw.find("](", i + 1), -1
            if close >= 0: end = raw.find(")", close + 2)
            if end >= 0 and end < hi:
                flush(); add_run(raw, i + 1, close, "existing-link", runs); i = end + 1; continue
        if raw[i] in "`$":
            end = raw.find(raw[i], i + 1)
            if end >= 0 and end < hi:
                flush(); add_run(raw, i + 1, end, "inline-code" if raw[i] == "`" else "inline-math", runs); i = end + 1; continue
        if raw[i] == "\\" and i + 1 < hi:
            text += raw[i + 1]; chars.append((i, i + 2)); i += 2; continue
        if raw.startswith(("**", "__"), i): flush(); i += 2; continue
        if raw[i] in "*_": flush(); i += 1; continue
        text += raw[i]; chars.append((i, i + 1)); i += 1
    flush()

def render(raw):
    runs, offset, fence, display = [], 0, False, False
    for full in raw.splitlines(keepends=True) or [raw]:
        line = full.rstrip("\n"); stripped = line.strip()
        if stripped.startswith("```"): fence = not fence; offset += len(full); continue
        if stripped == "$$": display = not display; offset += len(full); continue
        if fence or display:
            add_run(raw, offset, offset + len(line), "fenced-code" if fence else "display-math", runs)
        elif line.lstrip().startswith("|") and "|" in line[1:]:
            start = 0
            for end, ch in enumerate(line + "|"):
                if ch == "|":
                    if end > start: inline(raw, offset + start, offset + end, "table-cell", runs)
                    start = end + 1
        else: inline(raw, offset, offset + len(line), "text", runs)
        offset += len(full)
    return runs

def choose(runs, pick):
    matches = [r for r in runs if pick["text"] in r["text"]]
    run = matches[pick.get("runOccurrence", 0)]
    at = run["text"].index(pick["text"])
    return run, at + pick.get("start", 0), at + pick.get("end", len(pick["text"]))

def patch(raw, runs, pick, href, expected, actual):
    if expected != actual: raise Refusal("stale revision")
    run, start, end = choose(runs, pick)
    if run["context"] not in ("text", "table-cell"): raise Refusal("unsupported selection context: " + run["context"])
    if start == end: raise Refusal("empty selection")
    chars = run["chars"][start:end]
    if not chars: raise Refusal("unmapped DOM range")
    lo, hi = chars[0][0], chars[-1][1]
    return raw[:lo] + "[" + raw[lo:hi] + "](" + href + ")" + raw[hi:], lo, hi

fixtures = json.loads((Path(__file__).parent / "fixtures.json").read_text(encoding="utf-8"))
for f in fixtures:
    try:
        result, lo, hi = patch(f["raw"], render(f["raw"]), f["pick"], f["href"], 7, f.get("actualRevision", 7))
        if "refusal" in f: raise AssertionError(f"{f['name']}: expected refusal")
        assert result == f["expected"], f["name"]
        needle = "[" + f["raw"][lo:hi] + "](" + f["href"] + ")"; at = result.index(needle)
        assert result[:at] == f["raw"][:lo] and result[at + len(needle):] == f["raw"][hi:], f["name"]
    except Refusal as error:
        assert f.get("refusal") == str(error), f"{f['name']}: {error}"
print(f"PASS {len(fixtures)}/{len(fixtures)}: source-mapped selection patches and refusals verified")
