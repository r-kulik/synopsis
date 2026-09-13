"""UI-independent draft controller used by a browser tab host.

Saved text is deliberately not cached here.  Callers hydrate it from S02's
snapshot, retain only a dirty draft per open tab, and call save_markdown with
the revision that was rendered/edited.
"""
from dataclasses import dataclass
from typing import Callable


@dataclass
class Draft:
    note_id: str
    base_revision: int
    text: str
    dirty: bool = False
    save_error: str | None = None


class DraftTabs:
    def __init__(self): self._drafts: dict[str, Draft] = {}

    def open(self, note_id: str, saved_markdown: str, revision: int) -> Draft:
        current = self._drafts.get(note_id)
        if current is None:
            current = self._drafts[note_id] = Draft(note_id, revision, saved_markdown)
        return current

    def edit(self, note_id: str, text: str) -> Draft:
        draft = self._drafts[note_id]; draft.text = text; draft.dirty = True
        return draft

    def close_state(self, note_id: str) -> str:
        return "confirm" if self._drafts[note_id].dirty else "close"

    def discard(self, note_id: str) -> None: self._drafts.pop(note_id, None)

    def save(self, note_id: str, save_markdown: Callable[[str, str, int], object]) -> object:
        draft = self._drafts[note_id]
        try:
            saved = save_markdown(note_id, draft.text, draft.base_revision)
        except Exception as exc:
            draft.save_error = str(exc)
            raise
        draft.base_revision = saved.revision; draft.dirty = False; draft.save_error = None
        return saved
