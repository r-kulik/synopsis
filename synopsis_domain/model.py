from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import NewType

CourseId = NewType("CourseId", str)
NoteId = NewType("NoteId", str)
CardId = NewType("CardId", str)
LectureBoxId = NewType("LectureBoxId", str)
EdgeId = NewType("EdgeId", str)
FactId = NewType("FactId", str)
SourceId = NewType("SourceId", str)
AssetId = NewType("AssetId", str)

SCHEMA_VERSION = 1


class NoteKind(StrEnum):
    LECTURE = "lecture"
    CONCEPT = "concept"
    EXTERNAL_CONCEPT = "externalConcept"
    EXAMPLE = "example"
    TASK = "task"


class EdgeKind(StrEnum):
    CONTEXTUAL = "contextual"
    HIERARCHICAL = "hierarchical"
    MENTION = "mention"
    EXAMPLE_ATTACHMENT = "exampleAttachment"
    TASK_ATTACHMENT = "taskAttachment"


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class RelativeControlPoint:
    u: float
    v: float


@dataclass
class EdgeGeometry:
    """Polyline controls relative to card endpoints; see ADR-001 D-10."""
    control_points: list[RelativeControlPoint] = field(default_factory=list)
    routing: str = "polyline"


@dataclass
class Course:
    id: CourseId
    title: str
    schema_version: int = SCHEMA_VERSION
    saved_revision: int = 0
    settings: dict = field(default_factory=dict)


@dataclass
class Note:
    id: NoteId
    course_id: CourseId
    kind: NoteKind
    title: str
    summary: str
    markdown: str
    revision: int = 0
    defined_in_lecture_note_id: NoteId | None = None


@dataclass
class Card:
    id: CardId
    course_id: CourseId
    note_id: NoteId
    position: Point
    size: Point = Point(160, 72)
    lecture_box_id: LectureBoxId | None = None
    appearance: dict | None = None


@dataclass
class LectureBox:
    id: LectureBoxId
    course_id: CourseId
    note_id: NoteId
    position: Point
    size: Point


@dataclass
class Edge:
    id: EdgeId
    course_id: CourseId
    kind: EdgeKind
    source_card_id: CardId
    target_card_id: CardId
    label: str | None = None
    geometry: EdgeGeometry = field(default_factory=EdgeGeometry)


@dataclass
class Fact:
    id: FactId
    course_id: CourseId
    owner_note_id: NoteId
    markdown: str


@dataclass
class Asset:
    id: AssetId
    course_id: CourseId
    media_type: str
    relative_path: str
    original_name: str
    byte_length: int
    sha256: str | None = None


@dataclass
class Source:
    id: SourceId
    course_id: CourseId
    title: str
    asset_id: AssetId
    page_count: int | None = None


@dataclass(frozen=True)
class LectureSourceAttachment:
    lecture_note_id: NoteId
    source_id: SourceId
    page: int | None = None


@dataclass
class CourseSnapshot:
    course: Course
    notes: dict[NoteId, Note] = field(default_factory=dict)
    cards: dict[CardId, Card] = field(default_factory=dict)
    lecture_boxes: dict[LectureBoxId, LectureBox] = field(default_factory=dict)
    edges: dict[EdgeId, Edge] = field(default_factory=dict)
    facts: dict[FactId, Fact] = field(default_factory=dict)
    sources: dict[SourceId, Source] = field(default_factory=dict)
    assets: dict[AssetId, Asset] = field(default_factory=dict)
    lecture_source_attachments: list[LectureSourceAttachment] = field(default_factory=list)

