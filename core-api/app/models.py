"""Data model. Identifiers stored in the database (permission keys, status keys, role keys) are stable English
strings and are never translated; labels live in lookup tables or the frontend."""
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

TS = DateTime(timezone=True)


# --------------------------------------------------------------------------------------------- identity / RBAC
class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    rank: Mapped[int] = mapped_column(Integer, default=0)  # staff hierarchy: nobody acts on equal or higher rank
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # system roles can be edited but not deleted
    permissions: Mapped[list["RolePermission"]] = relationship(cascade="all, delete-orphan")


class Permission(Base):
    __tablename__ = "permissions"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    description: Mapped[str] = mapped_column(Text, default="")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_key: Mapped[str] = mapped_column(ForeignKey("permissions.key", ondelete="CASCADE"), primary_key=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    citizen_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    discord_id: Mapped[str | None] = mapped_column(String(30), unique=True)
    email: Mapped[str | None] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(120))
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)  # bump to invalidate every issued token
    source: Mapped[str] = mapped_column(String(20), default="local")  # local | fivem | legacy
    # employment mirror (QBCore stays authoritative in FiveM-linked mode)
    employment_job: Mapped[str | None] = mapped_column(String(50))
    employment_grade: Mapped[int | None] = mapped_column(Integer)
    employment_status: Mapped[str] = mapped_column(String(20), default="active")  # active | suspended | former
    language: Mapped[str] = mapped_column(String(5), default="en")
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(TS)
    role: Mapped[Role | None] = relationship()


class UserPermission(Base):
    """Individual grant or deny on top of the role. A deny always wins."""
    __tablename__ = "user_permissions"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    permission_key: Mapped[str] = mapped_column(ForeignKey("permissions.key", ondelete="CASCADE"), primary_key=True)
    effect: Mapped[str] = mapped_column(String(5))  # grant | deny
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class JobGradeMapping(Base):
    """Employment (FiveM job + grade) -> application role. Employment grade, app role and individual
    permissions are three separate concepts."""
    __tablename__ = "job_grade_mappings"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(50))
    grade_level: Mapped[int] = mapped_column(Integer)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    __table_args__ = (UniqueConstraint("job_name", "grade_level"),)


# --------------------------------------------------------------------------------------------- configuration
class LookupValue(Base):
    """Admin-editable vocabularies: investigation_status, investigation_type, article_type."""
    __tablename__ = "lookup_values"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(50))
    label_en: Mapped[str] = mapped_column(String(100))
    label_fr: Mapped[str] = mapped_column(String(100), default="")
    label_ar: Mapped[str] = mapped_column(String(100), default="")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("kind", "key"),)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True)
    label_en: Mapped[str] = mapped_column(String(100))
    label_fr: Mapped[str] = mapped_column(String(100), default="")
    label_ar: Mapped[str] = mapped_column(String(100), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkflowTransition(Base):
    """Configurable editorial workflow. A transition is allowed when the actor holds `permission_key`;
    `independent` additionally forbids the article's author (and assignees) from performing it."""
    __tablename__ = "workflow_transitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_status: Mapped[str] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    permission_key: Mapped[str] = mapped_column(String(80))
    independent: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_note: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("from_status", "to_status"),)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


# --------------------------------------------------------------------------------------------- articles
class Article(Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    subtitle: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    article_type: Mapped[str] = mapped_column(String(30), default="news")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=list)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    is_breaking: Mapped[bool] = mapped_column(Boolean, default=False)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    legacy_author_name: Mapped[str | None] = mapped_column(String(120))  # when the legacy author is not a known user
    cover_image_url: Mapped[str | None] = mapped_column(Text)
    cover_caption: Mapped[str] = mapped_column(String(300), default="")
    cover_credit: Mapped[str] = mapped_column(String(200), default="")
    source_refs: Mapped[list] = mapped_column(JSONB, default=list)
    internal_notes: Mapped[str] = mapped_column(Text, default="")  # never sent to public readers
    scheduled_for: Mapped[datetime | None] = mapped_column(TS)
    published_at: Mapped[datetime | None] = mapped_column(TS)
    published_destination: Mapped[str | None] = mapped_column(String(100))
    correction_note: Mapped[str | None] = mapped_column(Text)
    corrected_at: Mapped[datetime | None] = mapped_column(TS)
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic concurrency
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), onupdate=func.now())
    # migration bookkeeping
    imported_from_legacy: Mapped[bool] = mapped_column(Boolean, default=False)
    legacy_hash: Mapped[str | None] = mapped_column(String(64))
    platform_modified: Mapped[bool] = mapped_column(Boolean, default=False)

    author: Mapped[User | None] = relationship(foreign_keys=[author_id])
    category: Mapped[Category | None] = relationship()
    __table_args__ = (Index("ix_articles_status_published", "status", "published_at"),)


class ArticleAssignee(Base):
    __tablename__ = "article_assignees"
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)


class ArticleRevision(Base):
    __tablename__ = "article_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    subtitle: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    saved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    change_note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    __table_args__ = (UniqueConstraint("article_id", "revision_no"),)


class ArticleEvent(Base):
    """Approval / review / publication history. Append-only."""
    __tablename__ = "article_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(30))  # transition | comment | correction | assignment
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text, default="")
    feedback: Mapped[list] = mapped_column(JSONB, default=list)  # [{"field": "body", "comment": "..."}]
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class ArticleAutosave(Base):
    __tablename__ = "article_autosaves"
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    base_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), onupdate=func.now())


class ArticleInvestigation(Base):
    __tablename__ = "article_investigations"
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), primary_key=True)


class ArticleComment(Base):
    """Reader comments (public side of the legacy panel)."""
    __tablename__ = "article_comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    citizen_id: Mapped[str] = mapped_column(String(50))
    author_name: Mapped[str] = mapped_column(String(100))
    comment: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    imported_from_legacy: Mapped[bool] = mapped_column(Boolean, default=False)
    legacy_hash: Mapped[str | None] = mapped_column(String(64))


class ArticleLike(Base):
    __tablename__ = "article_likes"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    citizen_id: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    imported_from_legacy: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("article_id", "citizen_id"),)


# --------------------------------------------------------------------------------------------- investigations
class Investigation(Base):
    __tablename__ = "investigations"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(30), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text, default="")
    inv_type: Mapped[str] = mapped_column(String(50), default="general")
    status: Mapped[str] = mapped_column(String(50), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(10), default="normal")  # low | normal | high | urgent
    classification: Mapped[str] = mapped_column(String(15), default="standard")  # standard | restricted | confidential
    opened_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    target_date: Mapped[date | None] = mapped_column(Date)
    closed_at: Mapped[datetime | None] = mapped_column(TS)
    closure_note: Mapped[str] = mapped_column(Text, default="")
    findings: Mapped[str] = mapped_column(Text, default="")
    open_questions: Mapped[str] = mapped_column(Text, default="")
    conclusions: Mapped[str] = mapped_column(Text, default="")
    internal_notes: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), onupdate=func.now())
    imported_from_legacy: Mapped[bool] = mapped_column(Boolean, default=False)
    legacy_hash: Mapped[str | None] = mapped_column(String(64))
    platform_modified: Mapped[bool] = mapped_column(Boolean, default=False)
    legacy_meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class InvestigationParticipant(Base):
    __tablename__ = "investigation_participants"
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    access: Mapped[str] = mapped_column(String(10), default="read")  # read | write | lead
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    added_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class InvestigationEntry(Base):
    """Timeline entry. `verification` is set by people only, never by an AI model."""
    __tablename__ = "investigation_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    entry_type: Mapped[str] = mapped_column(String(30), default="note")  # note | event | interview | document | correction
    event_date: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    content: Mapped[str] = mapped_column(Text)
    verification: Mapped[str] = mapped_column(String(20), default="unverified_claim")
    source_ref: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str] = mapped_column(Text, default="")
    restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    correction_of_id: Mapped[int | None] = mapped_column(ForeignKey("investigation_entries.id"))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    legacy_author_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(TS)
    imported_from_legacy: Mapped[bool] = mapped_column(Boolean, default=False)
    legacy_hash: Mapped[str | None] = mapped_column(String(64))
    platform_modified: Mapped[bool] = mapped_column(Boolean, default=False)
    legacy_meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class InvestigationTask(Base):
    __tablename__ = "investigation_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="task")  # lead | task | follow_up
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text, default="")
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(15), default="open")  # open | done | dropped
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(TS)


class Source(Base):
    """General source record: pseudonymous reference + assessment. The real identity lives ONLY in
    SourceIdentity, behind a separate permission, and every read is audited."""
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40))  # e.g. "SRC-A1"; never a real name
    description: Mapped[str] = mapped_column(Text, default="")
    reliability: Mapped[str] = mapped_column(String(20), default="unassessed")  # unassessed | low | medium | high | proven
    assessment_notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    __table_args__ = (UniqueConstraint("investigation_id", "code"),)


class SourceIdentity(Base):
    __tablename__ = "source_identities"
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    identity: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), onupdate=func.now())


# --------------------------------------------------------------------------------------------- audit
class AuditLog(Base):
    """Append-only: the API exposes no update or delete."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    investigation_id: Mapped[int | None] = mapped_column(Integer, index=True)  # lets audit reads honour record access


# ------------------------------------------------------------------------------------------------- Phase 3
class EvidenceItem(Base):
    """A stored file. Content lives on disk under a random name; the database keeps the hash so tampering is detectable.
    Items are never hard-deleted (chain of custody): they are archived."""
    __tablename__ = "evidence_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    entry_id: Mapped[int | None] = mapped_column(ForeignKey("investigation_entries.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(15))  # image | document | audio | video | text
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(64), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class EvidenceCustody(Base):
    """Append-only custody log for one evidence item."""
    __tablename__ = "evidence_custody"
    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence_items.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(20))  # uploaded | downloaded | restricted | unrestricted | archived | restored | integrity_ok | integrity_failed
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(String(500), default="")
    at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class Notification(Base):
    """In-app notification. `title` is a snapshot taken only for recipients who could already see the record."""
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_notification_dedupe"), Index("ix_notifications_user_unread", "user_id", "read_at"))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(255), default="")
    link: Mapped[str] = mapped_column(String(200), default="")
    dedupe_key: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(TS)


# ------------------------------------------------------------------------------------------------- Phase 4
class AiRun(Base):
    """One AI suggestion. The prompt is NOT stored (only its hash and size); the output is, because the person asked for it.
    Nothing in this table is ever applied to an article or investigation automatically."""
    __tablename__ = "ai_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task: Mapped[str] = mapped_column(String(30))
    subject_type: Mapped[str] = mapped_column(String(15))  # article | investigation
    subject_id: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100), default="")
    input_chars: Mapped[int] = mapped_column(Integer, default=0)
    input_sha256: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(10), default="ok")  # ok | failed
    output: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    unsupported_citations: Mapped[list] = mapped_column(JSONB, default=list)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    disposition: Mapped[str] = mapped_column(String(10), default="pending")  # pending | accepted | rejected (set by the person)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), index=True)
    disposition_at: Mapped[datetime | None] = mapped_column(TS)
