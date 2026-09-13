from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import parse_qs, urlencode, urlparse


@dataclass(frozen=True)
class InternalAddress:
    resource: str
    id: str
    page: int | None = None


def make_internal_url(resource: str, id: str, *, page: int | None = None) -> str:
    if resource not in {"note", "source", "fact", "asset"} or not isinstance(id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", id):
        raise ValueError("invalid internal address components")
    if page is not None and (type(page) is not int or page < 1 or resource != "source"):
        raise ValueError("page must be a positive integer")
    return f"synopsis://{resource}/{id}" + (f"?{urlencode({'page': page})}" if page else "")


def parse_internal_url(raw: str) -> InternalAddress | None:
    """Returns None for malformed/user-authored URLs. Callers must preserve their Markdown."""
    if not isinstance(raw,str) or not re.fullmatch(r"synopsis://(?:note|source|fact|asset)/[A-Za-z0-9_-]{1,128}(?:\?page=[1-9][0-9]*)?", raw): return None
    parsed = urlparse(raw)
    if parsed.scheme != "synopsis" or parsed.netloc not in {"note", "source", "fact", "asset"}:
        return None
    if not parsed.path.startswith("/") or parsed.path.count("/") != 1 or not parsed.path[1:]:
        return None
    query = parse_qs(parsed.query, keep_blank_values=True)
    if set(query) - {"page"} or any(len(v) != 1 for v in query.values()):
        return None
    page = None
    if "page" in query:
        try: page = int(query["page"][0])
        except ValueError: return None
        if str(page) != query["page"][0] or page < 1: return None
    if page is not None and parsed.netloc != "source": return None
    return InternalAddress(parsed.netloc, parsed.path[1:], page)
