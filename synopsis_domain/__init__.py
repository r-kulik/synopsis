"""Stable S01 domain contracts for Synopsis; deliberately UI- and storage-agnostic."""

from .model import *  # noqa: F401,F403
from .service import CourseService, DomainError, ErrorCode
from .url import InternalAddress, parse_internal_url, make_internal_url

