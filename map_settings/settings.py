from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, field
from synopsis_domain import EdgeKind, NoteKind

DEFAULT_CARD_STYLES = {kind.value: {"fill": "#ffffff", "border": "#52657a", "text": "#18212b"} for kind in NoteKind if kind != NoteKind.LECTURE}
DEFAULT_EDGE_STYLES = {kind.value: {"stroke": "#52657a", "width": 2, "dash": "solid", "arrow": True, "label": True} for kind in EdgeKind}


@dataclass
class MapSettings:
    hidden_note_kinds: set[str] = field(default_factory=set)
    card_styles: dict[str, dict] = field(default_factory=lambda: deepcopy(DEFAULT_CARD_STYLES))
    edge_styles: dict[str, dict] = field(default_factory=lambda: deepcopy(DEFAULT_EDGE_STYLES))

    @classmethod
    def from_course_settings(cls, settings: dict) -> "MapSettings":
        raw = settings.get("map", {})
        result = cls(set(raw.get("hiddenNoteKinds", [])), deepcopy(raw.get("cardStyles", DEFAULT_CARD_STYLES)), deepcopy(raw.get("edgeStyles", DEFAULT_EDGE_STYLES)))
        return result

    def write_to_course_settings(self, settings: dict) -> None:
        settings["map"] = {"hiddenNoteKinds": sorted(self.hidden_note_kinds), "cardStyles": deepcopy(self.card_styles), "edgeStyles": deepcopy(self.edge_styles)}
