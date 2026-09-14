"""Official MCP SDK transport over stdio; no HTTP port or user-library access."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from .workspace import AuthoringWorkspace, workspace_lock


class Citation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    presentation_id: str = Field(description='ID returned by register_presentation')
    start_slide: int = Field(ge=1, description='First original slide, 1-based')
    end_slide: int | None = Field(default=None, ge=1, description='Inclusive last slide; omit for one slide')


def create_mcp(workspace: AuthoringWorkspace):
    mcp = FastMCP('Synopsis Authoring', instructions=(
        'Create courses only in an isolated draft workspace. Register presentations, then create lectures '
        'and notes with citations. Use returned IDs and URLs; do not write JSON or ZIP by hand. '
        'Call get_course to resume, get_note before update_note, validate_course and export_course at the end. '
        'Software validates structure, not the truth of generated educational content.'
    ))
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
    edit = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

    def evidence(citations):
        return [c.model_dump(exclude_none=True) for c in citations]

    @mcp.tool(annotations=write)
    def create_course(title: str) -> dict[str, Any]:
        """Create a NEW isolated draft course. Save its course_id; check list_courses before retrying."""
        return workspace.create_course(title)

    @mcp.tool(annotations=read)
    def list_courses() -> dict[str, Any]:
        """List only MCP draft courses, never the user's main Synopsis library."""
        return {'courses': workspace.list_courses()}

    @mcp.tool(annotations=write)
    def register_presentation(course_id: str, filename: str, slide_count: int, title: str = '') -> dict[str, Any]:
        """Record one source presentation after inspecting it; returns citation ID. Does not read/upload a file."""
        return workspace.register_presentation(course_id, filename, slide_count, title)

    @mcp.tool(annotations=read)
    def get_course(course_id: str) -> dict[str, Any]:
        """Recover draft IDs, note titles/types, source inventory, facts and graph edges."""
        return workspace.get_course(course_id)

    @mcp.tool(annotations=read)
    def get_note(course_id: str, note_id: str) -> dict[str, Any]:
        """Read body (without generated citations), complete markdown, citations, URL and current revision."""
        return workspace.get_note(course_id, note_id)

    @mcp.tool(annotations=write)
    def create_lecture(course_id: str, title: str, markdown: str, citations: list[Citation], summary: str = '') -> dict[str, Any]:
        """Create a lecture note AND a non-overlapping frame. Never use an ordinary card for a lecture."""
        return workspace.add_note(course_id, 'lecture', title, markdown, evidence(citations), summary=summary)

    @mcp.tool(annotations=write)
    def add_concept(course_id: str, title: str, markdown: str, citations: list[Citation],
                    lecture_id: str | None = None, summary: str = '', external: bool = False) -> dict[str, Any]:
        """Create a concept/theorem/method and its card; external=True only for prerequisites OUTSIDE this course."""
        return workspace.add_note(course_id, 'externalConcept' if external else 'concept', title,
                                  markdown, evidence(citations), lecture_id, summary)

    @mcp.tool(annotations=write)
    def add_example(course_id: str, title: str, markdown: str, citations: list[Citation],
                    lecture_id: str | None = None, summary: str = '') -> dict[str, Any]:
        """Create a worked example and its card. Connect it to a concept with exampleAttachment."""
        return workspace.add_note(course_id, 'example', title, markdown, evidence(citations), lecture_id, summary)

    @mcp.tool(annotations=write)
    def add_task(course_id: str, title: str, markdown: str, citations: list[Citation],
                 lecture_id: str | None = None, summary: str = '') -> dict[str, Any]:
        """Create an exercise and its card. Do not invent an original source solution."""
        return workspace.add_note(course_id, 'task', title, markdown, evidence(citations), lecture_id, summary)

    @mcp.tool(annotations=write)
    def add_fact(course_id: str, owner_note_id: str, markdown: str, citations: list[Citation], label: str = 'Пояснение') -> dict[str, Any]:
        """Create an owner-scoped comment and automatically link it from the owner note; not a theorem card."""
        return workspace.add_fact(course_id, owner_note_id, markdown, evidence(citations), label)

    @mcp.tool(annotations=edit)
    def update_note(course_id: str, note_id: str, markdown: str, expected_revision: int,
                    citations: list[Citation] | None = None) -> dict[str, Any]:
        """Replace the body using the revision from get_note. Preserve facts/links; citations appended by server."""
        return workspace.update_note(course_id, note_id, markdown, expected_revision,
                                     evidence(citations) if citations is not None else None)

    @mcp.tool(annotations=write)
    def connect(course_id: str, source_note_id: str, target_note_id: str,
                kind: Literal['contextual', 'hierarchical', 'mention', 'exampleAttachment', 'taskAttachment'], label: str) -> dict[str, Any]:
        """Connect note cards. Types: concept→concept; external→concept (mention); example/task→concept. No lecture endpoints."""
        return workspace.connect(course_id, source_note_id, target_note_id, kind, label)

    @mcp.tool(annotations=write)
    def attach_file(course_id: str, path: str, lecture_id: str | None = None) -> dict[str, Any]:
        """Attach a local PDF/PNG/JPEG/WebP from allowed input roots. PDF page count is parsed; returns a real internal URL."""
        return workspace.attach_file(course_id, path, lecture_id)

    @mcp.tool(annotations=read)
    def validate_course(course_id: str) -> dict[str, Any]:
        """Check structure, internal links and citation coverage. Coverage is not proof of semantic completeness."""
        return workspace.validate_course(course_id)

    @mcp.tool(annotations=write)
    def export_course(course_id: str) -> dict[str, Any]:
        """Validate, round-trip import in isolated storage, then produce a new .synopsis file. Never import to live library."""
        return workspace.export_course(course_id)

    return mcp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parent.parent / '.synopsis-mcp')
    parser.add_argument('--input-root', type=Path, action='append', default=[], help='Explicitly allow local attachment files from this directory')
    args = parser.parse_args()
    with workspace_lock(args.workspace):
        workspace = AuthoringWorkspace(args.workspace, args.input_root)
        create_mcp(workspace).run(transport='stdio')


if __name__ == '__main__':
    main()
