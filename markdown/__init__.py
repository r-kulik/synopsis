"""Stable, dependency-free Markdown profile metadata for Synopsis.

The raw string is always canonical.  This module intentionally does not expose
a rich-text document model: readers and future source-map consumers receive
raw offsets into that string.
"""

PROFILE = "CommonMark subset + GFM tables/strike/task lists + $/$$ math"
UNSUPPORTED = ("raw HTML", "footnotes", "diagrams", "custom math macros")


def is_remote_image(url: str) -> bool:
    return url.lower().startswith(("http://", "https://"))


def is_local_path_image(url: str) -> bool:
    return url.startswith(("file:", "./", "../", "\\\\")) or (len(url) > 2 and url[1:3] == ":\\")
