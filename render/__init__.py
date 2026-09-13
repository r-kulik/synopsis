"""Safe local reading renderer and deliberately bounded source-map API.

`SourceSpan` maps only ordinary inline text emitted by this renderer. Formulae,
code, image alt text and Markdown delimiters are explicitly unmapped; S05 must
refuse selections crossing them rather than infer an unsafe DOM mapping.
"""
from dataclasses import dataclass
from html import escape
import re
from markdown import is_local_path_image, is_remote_image
from synopsis_domain import CourseService, parse_internal_url


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    start: int
    end: int

@dataclass(frozen=True)
class SourceSpan:
    raw_start: int
    raw_end: int
    rendered_text: str
    selectable: bool = True

@dataclass(frozen=True)
class RenderedMarkdown:
    html: str
    spans: tuple[SourceSpan, ...]
    diagnostics: tuple[Diagnostic, ...]

_image = re.compile(r'!\[([^]]*)\]\(([^ )]+)(?:\s+"[^"]*")?\)')
_link = re.compile(r'(?<!!)\[([^]]+)\]\(([^ )]+)\)')
_math = re.compile(r'\$\$([\s\S]*?)\$\$|\$([^$\n]+)\$')
_bad_math = re.compile(r'\\(?:write18|input|include|html|href)\b')

def _resolver(snapshot):
    return CourseService(snapshot).resolve_internal_url

def render_markdown(raw: str, snapshot, *, asset_url=None) -> RenderedMarkdown:
    """Render profile v1 without executing HTML or fetching remote images."""
    resolve = _resolver(snapshot); diagnostics=[]; spans=[]
    asset_url = asset_url or (lambda asset_id: f"/api/courses/{snapshot.course.id}/assets/{asset_id}")
    def image(m):
        alt, url = m.group(1), m.group(2)
        if is_remote_image(url):
            diagnostics.append(Diagnostic("remoteImage", "Remote image is external and is not embedded", m.start(), m.end()))
            return f'<span class="image-diagnostic">[remote image: {escape(alt)}]</span>'
        if is_local_path_image(url):
            diagnostics.append(Diagnostic("localImagePath", "Local file paths are not portable; import an asset", m.start(), m.end()))
            return f'<span class="image-diagnostic">[local image path: {escape(alt)}]</span>'
        address=parse_internal_url(url)
        if address and address.resource == "asset" and resolve(url):
            return f'<img alt="{escape(alt)}" src="{escape(asset_url(address.id), quote=True)}">'
        diagnostics.append(Diagnostic("invalidImage", "Image asset is missing or invalid", m.start(), m.end()))
        return f'<span class="invalid-link">[missing image: {escape(alt)}]</span>'
    def link(m):
        label, url=m.group(1), m.group(2); address=parse_internal_url(url)
        if address:
            if resolve(url): return f'<a class="internal-link" href="{escape(url, quote=True)}">{escape(label)}</a>'
            diagnostics.append(Diagnostic("invalidInternalUrl", "Internal target is missing or invalid", m.start(), m.end()))
            return f'<span class="invalid-link" title="Internal target is missing">{escape(label)}</span>'
        return f'<a href="{escape(url, quote=True)}" rel="noreferrer">{escape(label)}</a>'
    def math(m):
        value=m.group(1) if m.group(1) is not None else m.group(2); display=m.group(1) is not None
        if _bad_math.search(value):
            diagnostics.append(Diagnostic("invalidFormula", "Unsupported or unsafe formula command", m.start(), m.end()))
            return f'<code class="formula-error">{escape(m.group(0))}</code>'
        tag="div" if display else "span"; return f'<{tag} class="math">{escape(value)}</{tag}>'
    # Escape first: Markdown is text, never an HTML execution channel.  The
    # syntax delimiters used by this small profile remain intact after escape.
    text=_image.sub(image, escape(raw)); text=_link.sub(link, text); text=_math.sub(math, text)
    # No raw HTML execution. Simple headings, tables, lists and paragraphs are local HTML.
    lines=[]
    for line in text.splitlines():
        if line.startswith("### "): lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "): lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "): lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("- "): lines.append(f"<li>{line[2:]}</li>")
        elif line.startswith("|"): lines.append(f"<div class=\"gfm-table-row\">{line}</div>")
        elif line: lines.append(f"<p>{line}</p>")
        else: lines.append("")
    # Offset calculation is deliberately based on raw lines, never generated
    # HTML; source spans are invalidated for Markdown constructs we do not map.
    raw_offset = 0
    for raw_line in raw.splitlines(keepends=True):
        visible = raw_line.rstrip("\r\n")
        if visible and not any(x in visible for x in ("[", "`", "$", "!")):
            spans.append(SourceSpan(raw_offset, raw_offset + len(visible), visible))
        raw_offset += len(raw_line)
    return RenderedMarkdown("\n".join(lines), tuple(spans), tuple(diagnostics))
