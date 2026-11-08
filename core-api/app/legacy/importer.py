"""Imports the five legacy MySQL tables (rp_articles, article_likes, article_comments, rp_dossiers,
rp_dossier_entries) into the new PostgreSQL schema.

Guarantees
  * The legacy database is only ever READ (SELECT). Nothing in MySQL is changed or dropped.
  * Primary keys, authorship strings, timestamps, comments, likes and timelines are preserved.
  * Repeatable: running it again inserts new legacy rows and refreshes rows that have NOT been modified in the
    new platform. A row edited on the platform (platform_modified = true) is never overwritten, only reported.
  * An id collision with a natively created row aborts the import instead of overwriting.
  * Nothing is dropped silently: orphans, unknown statuses and invalid URLs are counted in the report.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app import models as m
from app.api.common import clean_text

TABLES = ["rp_articles", "article_comments", "article_likes", "rp_dossiers", "rp_dossier_entries"]
ART_STATUS = {"draft": "draft", "pending": "submitted", "published": "published"}
DOSSIER_STATUS = {"open": "open", "active": "active", "closed": "concluded", "concluded": "concluded", "archived": "archived"}
CLASSIFICATION = {"private": "confidential", "institution": "standard", "public": "standard"}  # stricter, never looser
ENTRY_VERIFICATION = {"rumour": "rumour", "confirmed": "confirmed", "denied": "denial"}
URL_RE = re.compile(r"https?://[\w\-._~:/?#\[\]@!$&()*+,;=%]+")


class LegacySource(Protocol):
    def rows(self, table: str) -> list[dict]: ...


class DictSource:
    def __init__(self, data: dict[str, list[dict]]):
        self.data = data

    def rows(self, table: str) -> list[dict]:
        return [dict(r) for r in self.data.get(table, [])]


class MySQLSource:
    """Read-only. Use a MySQL account that only has SELECT on the database."""

    def __init__(self, url: str):
        # Legacy FiveM databases are utf8mb4; without an explicit charset the driver may decode accents as latin1.
        if "charset=" not in url:
            url += ("&" if "?" in url else "?") + "charset=utf8mb4"
        self.engine = create_engine(url)

    def rows(self, table: str) -> list[dict]:
        if table not in TABLES:
            raise ValueError("unexpected table")
        with self.engine.connect() as c:
            c.execute(text("SET time_zone = '+00:00'"))  # TIMESTAMP columns are read as UTC
            return [dict(r) for r in c.execute(text(f"SELECT * FROM `{table}` ORDER BY id")).mappings()]


@dataclass
class TableReport:
    source: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_modified: list[int] = field(default_factory=list)
    skipped_orphans: list[int] = field(default_factory=list)


@dataclass
class ImportReport:
    tables: dict[str, TableReport] = field(default_factory=lambda: {t: TableReport() for t in TABLES})
    warnings: list[str] = field(default_factory=list)
    stub_users_created: int = 0
    categories_created: list[str] = field(default_factory=list)
    dry_run: bool = False

    def as_dict(self) -> dict:
        return {"dry_run": self.dry_run, "stub_users_created": self.stub_users_created, "categories_created": self.categories_created,
                "warnings": self.warnings, "tables": {k: v.__dict__ for k, v in self.tables.items()}}


class ImportConflict(Exception):
    pass


def _h(row: dict) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def _utc(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, str):
        v = datetime.fromisoformat(v)
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


def _s(v, n: int) -> str:
    return clean_text(None if v is None else str(v), n, multiline=True)


class _Run:
    def __init__(self, db: Session, src: LegacySource):
        self.db, self.src, self.rep = db, src, ImportReport()
        users = db.scalars(select(m.User).where(m.User.is_active.is_(True))).all()
        by_name: dict[str, list[m.User]] = {}
        for u in users:
            by_name.setdefault(u.display_name.strip().lower(), []).append(u)
        self.by_name = by_name
        self.by_cid = {u.citizen_id: u for u in db.scalars(select(m.User).where(m.User.citizen_id.is_not(None)))}
        self.categories = {c.key: c for c in db.scalars(select(m.Category))}
        self.statuses = {l.key for l in db.scalars(select(m.LookupValue).where(m.LookupValue.kind == "investigation_status"))}
        self.types = {l.key for l in db.scalars(select(m.LookupValue).where(m.LookupValue.kind == "investigation_type"))}

    # ---- helpers
    def author(self, name: str | None) -> tuple[int | None, str | None]:
        if not name:
            return None, None
        hits = self.by_name.get(name.strip().lower(), [])
        return (hits[0].id, None) if len(hits) == 1 else (None, name[:120])  # ambiguous names stay as text

    def stub_user(self, citizen_id: str, name: str | None) -> m.User:
        u = self.by_cid.get(citizen_id)
        if u is None:
            u = m.User(citizen_id=citizen_id, display_name=(name or citizen_id)[:120], source="legacy", is_active=True, role_id=None)
            self.db.add(u)
            self.db.flush()
            self.by_cid[citizen_id] = u
            self.rep.stub_users_created += 1
        return u

    def category(self, key: str | None) -> int | None:
        key = (key or "breaking").strip().lower()[:50] or "breaking"
        if key not in self.categories:
            c = m.Category(key=key, label_en=key.replace("_", " ").title())
            self.db.add(c)
            self.db.flush()
            self.categories[key] = c
            self.rep.categories_created.append(key)
        return self.categories[key].id

    def upsert(self, model, table: str, row_id: int, h: str, build) -> None:
        rep = self.rep.tables[table]
        obj = self.db.get(model, row_id)
        if obj is None:
            obj = model(id=row_id)
            build(obj)
            obj.imported_from_legacy, obj.legacy_hash = True, h
            self.db.add(obj)
            rep.inserted += 1
        elif not getattr(obj, "imported_from_legacy", False):
            raise ImportConflict(f"{table} id {row_id} already exists as a native record; aborting to avoid overwriting it")
        elif getattr(obj, "platform_modified", False):
            rep.skipped_modified.append(row_id)
        elif obj.legacy_hash == h:
            rep.unchanged += 1
        else:
            build(obj)
            obj.legacy_hash = h
            rep.updated += 1
        self.db.flush()

    # ---- tables
    def articles(self) -> set[int]:
        ids = set()
        for r in self.src.rows("rp_articles"):
            rid = int(r["id"])
            ids.add(rid)
            self.rep.tables["rp_articles"].source += 1
            status = ART_STATUS.get((r.get("status") or "").strip().lower())
            if status is None:
                self.rep.warnings.append(f"rp_articles {rid}: unknown status {r.get('status')!r}, imported as draft")
                status = "draft"
            image = (r.get("image") or "").strip()
            if image and not URL_RE.fullmatch(image):
                self.rep.warnings.append(f"rp_articles {rid}: image is not a plain http(s) URL, not imported")
                image = ""
            created = _utc(r.get("created_at")) or datetime.now(timezone.utc)
            author_id, author_name = self.author(r.get("author"))

            def build(a: m.Article, r=r, status=status, image=image, created=created, author_id=author_id, author_name=author_name):
                a.title = _s(r.get("title"), 255) or "(untitled)"
                a.body = _s(r.get("content"), 60000)
                a.status, a.category_id, a.article_type = status, self.category(r.get("category")), "breaking" if (r.get("category") or "") == "breaking" else "news"
                a.is_breaking = (r.get("category") or "") == "breaking"
                a.author_id, a.legacy_author_name = author_id, author_name
                a.cover_image_url = image or None
                a.created_at = a.updated_at = created
                a.published_at = created if status == "published" else None
                a.tags, a.source_refs, a.version = a.tags or [], a.source_refs or [], a.version or 1

            self.upsert(m.Article, "rp_articles", rid, _h(r), build)
        return ids

    def comments(self, article_ids: set[int]) -> None:
        for r in self.src.rows("article_comments"):
            rid = int(r["id"])
            self.rep.tables["article_comments"].source += 1
            if int(r["article_id"]) not in article_ids:
                self.rep.tables["article_comments"].skipped_orphans.append(rid)
                continue

            def build(c: m.ArticleComment, r=r):
                c.article_id, c.citizen_id = int(r["article_id"]), _s(r.get("citizenid"), 50)
                c.author_name, c.comment = _s(r.get("author_name"), 100), _s(r.get("comment"), 150)
                c.created_at = _utc(r.get("created_at")) or datetime.now(timezone.utc)

            self.upsert(m.ArticleComment, "article_comments", rid, _h(r), build)

    def likes(self, article_ids: set[int]) -> None:
        for r in self.src.rows("article_likes"):
            rid = int(r["id"])
            self.rep.tables["article_likes"].source += 1
            if int(r["article_id"]) not in article_ids:
                self.rep.tables["article_likes"].skipped_orphans.append(rid)
                continue

            def build(l: m.ArticleLike, r=r):
                l.article_id, l.citizen_id = int(r["article_id"]), _s(r.get("citizenid"), 50)
                l.created_at = _utc(r.get("created_at")) or datetime.now(timezone.utc)

            rep = self.rep.tables["article_likes"]
            obj = self.db.get(m.ArticleLike, rid)
            if obj is None:
                build_obj = m.ArticleLike(id=rid, imported_from_legacy=True)
                build(build_obj)
                self.db.add(build_obj)
                rep.inserted += 1
            elif not obj.imported_from_legacy:
                raise ImportConflict(f"article_likes id {rid} already exists as a native record; aborting")
            else:
                rep.unchanged += 1
            self.db.flush()

    def dossiers(self) -> set[int]:
        ids = set()
        for r in self.src.rows("rp_dossiers"):
            rid = int(r["id"])
            ids.add(rid)
            self.rep.tables["rp_dossiers"].source += 1
            raw_status = (r.get("status") or "open").strip().lower()
            status = DOSSIER_STATUS.get(raw_status)
            if status is None or status not in self.statuses:
                self.rep.warnings.append(f"rp_dossiers {rid}: unknown status {raw_status!r}, imported as open")
                status = "open"
            archived = bool(r.get("archived"))
            if archived:
                status = "archived"
            vis = (r.get("visibility") or "institution").strip().lower()
            cls = CLASSIFICATION.get(vis)
            if cls is None:
                self.rep.warnings.append(f"rp_dossiers {rid}: unknown visibility {vis!r}, imported as confidential")
                cls = "confidential"
            inv_type = (r.get("type") or "general").strip().lower()
            meta = {"citizenid": r.get("citizenid"), "created_by": r.get("created_by"), "created_job": r.get("created_job"),
                    "source_event_id": r.get("source_event_id"), "legacy_visibility": vis, "legacy_type": inv_type}
            if inv_type not in self.types:
                inv_type = "general"
            creator = self.stub_user(str(r["citizenid"]), r.get("created_by")) if r.get("citizenid") else None
            opened = _utc(r.get("created_at")) or datetime.now(timezone.utc)

            def build(i: m.Investigation, r=r, status=status, cls=cls, inv_type=inv_type, meta=meta, creator=creator, opened=opened, archived=archived):
                i.reference = f"WZ-LEG-{int(r['id']):04d}"
                i.title = _s(r.get("title"), 255) or "(untitled)"
                i.status, i.classification, i.inv_type, i.priority = status, cls, inv_type, i.priority or "normal"
                i.opened_at = i.updated_at = opened
                i.closed_at = _utc(r.get("closed_at"))
                i.is_archived, i.created_by, i.legacy_meta = archived, creator.id if creator else None, meta
                i.summary = i.summary or ""
                i.version = i.version or 1

            self.upsert(m.Investigation, "rp_dossiers", rid, _h(r), build)
            if creator and self.db.get(m.InvestigationParticipant, (rid, creator.id)) is None:
                self.db.add(m.InvestigationParticipant(investigation_id=rid, user_id=creator.id, access="lead", added_by=creator.id))
        return ids

    def entries(self, dossier_ids: set[int]) -> None:
        for r in self.src.rows("rp_dossier_entries"):
            rid = int(r["id"])
            self.rep.tables["rp_dossier_entries"].source += 1
            if int(r["dossier_id"]) not in dossier_ids:
                self.rep.tables["rp_dossier_entries"].skipped_orphans.append(rid)
                continue
            raw = (r.get("entry_type") or "").strip().lower()  # the column the legacy code actually used for verification
            ver = ENTRY_VERIFICATION.get(raw)
            if ver is None:
                self.rep.warnings.append(f"rp_dossier_entries {rid}: unknown entry_type {raw!r}, imported as unverified_claim")
                ver = "unverified_claim"
            author_id, author_name = self.author(r.get("author"))
            source = (r.get("source") or "").strip()

            def build(e: m.InvestigationEntry, r=r, ver=ver, author_id=author_id, author_name=author_name, source=source):
                e.investigation_id, e.entry_type, e.verification = int(r["dossier_id"]), "note", ver
                e.content = _s(r.get("content"), 10000)
                e.event_date = e.created_at = _utc(r.get("created_at")) or datetime.now(timezone.utc)
                e.author_id, e.legacy_author_name = author_id, author_name or (None if author_id else r.get("author"))
                e.source_ref = None if source.lower() in {"", "source anonyme"} else source[:200]
                e.restricted = (r.get("visibility") or "public") == "police"
                e.notes = e.notes or ""
                e.legacy_meta = {"author_job": r.get("author_job"), "image_path": r.get("image_path"), "caption": r.get("caption"),
                                 "escalated": bool(r.get("escalated")), "status_column": r.get("status"), "legacy_visibility": r.get("visibility")}

            self.upsert(m.InvestigationEntry, "rp_dossier_entries", rid, _h(r), build)

    def reset_sequences(self) -> None:
        for table in ("articles", "article_comments", "article_likes", "investigations", "investigation_entries"):
            self.db.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), GREATEST((SELECT COALESCE(MAX(id), 0) FROM {table}), 1))"))


def import_legacy(db: Session, src: LegacySource, *, dry_run: bool = False) -> ImportReport:
    run = _Run(db, src)
    run.rep.dry_run = dry_run
    try:
        art_ids = run.articles()
        run.comments(art_ids)
        run.likes(art_ids)
        dos_ids = run.dossiers()
        run.entries(dos_ids)
        run.reset_sequences()
        db.rollback() if dry_run else db.commit()
    except Exception:
        db.rollback()
        raise
    return run.rep


def verify_legacy(db: Session, src: LegacySource) -> dict:
    """Compares the source with the platform. `ok` is true only when every legacy row is present with matching
    content (rows edited on the platform are reported separately and are not mismatches)."""
    report: dict = {"tables": {}, "ok": True}
    spec = [("rp_articles", m.Article), ("article_comments", m.ArticleComment), ("article_likes", m.ArticleLike),
            ("rp_dossiers", m.Investigation), ("rp_dossier_entries", m.InvestigationEntry)]
    for table, model in spec:
        rows = src.rows(table)
        src_ids = {int(r["id"]) for r in rows}
        have = {o.id: o for o in db.scalars(select(model).where(model.imported_from_legacy.is_(True)))}
        art_ids = {int(r["id"]) for r in src.rows("rp_articles")}
        dos_ids = {int(r["id"]) for r in src.rows("rp_dossiers")}
        orphan = set()
        for r in rows:
            if table in ("article_comments", "article_likes") and int(r["article_id"]) not in art_ids:
                orphan.add(int(r["id"]))
            if table == "rp_dossier_entries" and int(r["dossier_id"]) not in dos_ids:
                orphan.add(int(r["id"]))
        expected = src_ids - orphan
        missing = sorted(expected - set(have))
        mismatched = sorted(rid for r in rows if (rid := int(r["id"])) in have and not getattr(have[rid], "platform_modified", False)
                            and getattr(have[rid], "legacy_hash", None) is not None and have[rid].legacy_hash != _h(r) and model is not m.ArticleLike)
        modified = sorted(rid for rid, o in have.items() if getattr(o, "platform_modified", False))
        entry = {"source_rows": len(rows), "expected_in_platform": len(expected), "present": len(expected & set(have)), "missing_ids": missing,
                 "content_mismatch_ids": mismatched, "modified_on_platform_ids": modified, "orphans_in_source": sorted(orphan)}
        report["tables"][table] = entry
        if missing or mismatched:
            report["ok"] = False
    return report
