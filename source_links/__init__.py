"""PDF-only source links and external-opening intents (never an embedded viewer)."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from synopsis_domain import (AssetId, CourseService, DomainError, ErrorCode, LectureSourceAttachment,
                             NoteId, NoteKind, Source, SourceId, make_internal_url)


@dataclass(frozen=True)
class ExternalPdfIntent:
    url: str
    page: int | None
    target: str = "_blank"
    embedded: bool = False


def _valid_source(service: CourseService, source_id: SourceId, page: int | None = None) -> Source:
    try: source = service.state.sources[source_id]
    except KeyError: raise DomainError(ErrorCode.NOT_FOUND, "source does not exist")
    asset = service.state.assets.get(source.asset_id)
    if source.course_id != service.state.course.id or asset is None or asset.course_id != source.course_id:
        raise DomainError(ErrorCode.COURSE_MISMATCH, "source asset is unavailable in this course")
    if asset.media_type.lower() != "application/pdf":
        raise DomainError(ErrorCode.VALIDATION, "source asset must be a PDF")
    if page is not None and (page < 1 or (source.page_count is not None and page > source.page_count)):
        raise DomainError(ErrorCode.VALIDATION, "PDF page is invalid")
    return source


def make_source_url(service: CourseService, source_id: SourceId, page: int | None = None) -> str:
    _valid_source(service, source_id, page)
    return make_internal_url("source", source_id, page=page)


def attach_pdf_to_lecture(service: CourseService, lecture_note_id: NoteId, source_id: SourceId,
                          page: int | None = None) -> LectureSourceAttachment:
    """Attach an existing validated PDF; replacement means a new Source, never byte mutation."""
    source = _valid_source(service, source_id, page)
    def command():
        lecture = service._note(lecture_note_id)
        if lecture.kind != NoteKind.LECTURE:
            raise DomainError(ErrorCode.VALIDATION, "a PDF source can only be attached to a lecture")
        if lecture.course_id != source.course_id:
            raise DomainError(ErrorCode.COURSE_MISMATCH, "lecture and source must share course")
        attachment = LectureSourceAttachment(lecture_note_id, source_id, page)
        if attachment not in service.state.lecture_source_attachments:
            service.state.lecture_source_attachments.append(attachment)
        return attachment
    return service._atomic(command)


def external_open_intent(service: CourseService, source_id: SourceId, page: int | None = None) -> ExternalPdfIntent:
    source = _valid_source(service, source_id, page)
    path = f"/api/courses/{quote(str(source.course_id), safe='')}/assets/{quote(str(source.asset_id), safe='')}"
    # Fragment is a best-effort hint for an external PDF handler; the UI also displays page.
    return ExternalPdfIntent(path + (f"#page={page}" if page else ""), page)
