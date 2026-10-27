"""도메인 열거형. DB에서는 PostgreSQL enum 대신 `text + CHECK`로 저장한다 (architecture.md 9장)."""

from enum import StrEnum


class SignInProvider(StrEnum):
    PASSWORD = "password"
    GOOGLE = "google.com"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DELETING = "deleting"


class QuestionDepth(StrEnum):
    BASIC = "basic"
    DEEP = "deep"


class ProjectColor(StrEnum):
    INDIGO = "indigo"
    LAVENDER = "lavender"
    CYAN = "cyan"


class FileType(StrEnum):
    PDF = "pdf"
    PPTX = "pptx"


class MaterialStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    QUEUED = "queued"
    EXTRACTING = "extracting"
    GENERATING_CONCEPTS = "generating_concepts"
    READY = "ready"
    FAILED = "failed"


class FailureCode(StrEnum):
    UNSUPPORTED_FORMAT = "unsupported_format"
    FILE_TOO_LARGE = "file_too_large"
    TOO_MANY_PAGES = "too_many_pages"
    NO_EXTRACTABLE_TEXT = "no_extractable_text"
    CORRUPTED_FILE = "corrupted_file"
    LLM_FAILED = "llm_failed"
    INTERNAL_ERROR = "internal_error"


class ConceptState(StrEnum):
    NOT_STUDIED = "not_studied"
    PARTIAL = "partial"
    MISCONCEPTION = "misconception"
    UNDERSTOOD = "understood"


class Importance(StrEnum):
    CORE = "core"
    SUPPORTING = "supporting"


class Verdict(StrEnum):
    MET = "met"
    PARTIAL = "partial"
    MISSING = "missing"
    CONTRADICTED = "contradicted"


class SessionStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABORTED = "aborted"


class EndReason(StrEnum):
    UNDERSTOOD = "understood"
    MAX_FOLLOWUPS = "max_followups"
    USER_EXIT = "user_exit"
    SUPERSEDED = "superseded"
    STALE = "stale"


class MessageRole(StrEnum):
    ANSWER = "answer"
    QUESTION = "question"
