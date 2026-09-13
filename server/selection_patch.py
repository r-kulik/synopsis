"""Validate browser UTF-16 ranges before a revision-aware raw Markdown patch.

The browser uses remark text-node positions. The server checks revision and
raw text independently, and refuses links/code/math/HTML or block crossings.
"""
import html
import re
from synopsis_domain import DomainError, ErrorCode

_protected = re.compile(
    r"(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[^\n]*(?:\n|$)"
    r"|`+[^`]*`+|\$\$[\s\S]*?\$\$|\$[^\n$]+\$"
    r"|!?\[(?:\\.|[^\]\\])*\]\([^\n)]*\)|<[^>\n]*>"
)

def _offset(raw, value):
    if type(value) is not int or value < 0: raise ValueError("Некорректные границы выделения")
    encoded = raw.encode("utf-16-le")
    if value*2 > len(encoded): raise ValueError("Выделение выходит за границы конспекта")
    try: return len(encoded[:value*2].decode("utf-16-le"))
    except UnicodeDecodeError as exc: raise ValueError("Выделение разрезает символ Unicode") from exc

def checked_browser_range(note, data):
    if note.revision != data["revision"]:
        raise DomainError(ErrorCode.REVISION_CONFLICT, "Конспект изменился. Обновите чтение и выделите текст заново.")
    start,end = _offset(note.markdown,data["raw_start"]),_offset(note.markdown,data["raw_end"])
    raw = note.markdown[start:end]
    if not raw or start>=end or "\n" in raw or "\r" in raw:
        raise ValueError("Выделите непустой текст внутри одного фрагмента")
    if any(start < m.end() and end > m.start() for m in _protected.finditer(note.markdown)):
        raise ValueError("Внутри ссылок, кода, формул и HTML выделение недоступно")
    plain = re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@[\]\\^_`{|}~])",r"\1",raw)
    plain = html.unescape(plain)
    if plain != data["selected_text"]:
        raise ValueError("Выделение не совпадает с сохранённым текстом")
    if re.search(r"(?<!\\)[\[\]`*_$]",raw):
        raise ValueError("Выделение пересекает границу форматирования")
    return start,end,raw
