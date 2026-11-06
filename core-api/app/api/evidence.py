"""Evidence library. Files are stored under random names outside any served folder, hashed on upload, never served inline
(always as an attachment), never hard-deleted, and every access is written to the custody log and the audit log."""
import hashlib
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import models as m
from app.api.common import NOT_FOUND, clean_text
from app.api.investigations import _load
from app.config import get_settings
from app.deps import get_ctx
from app.services import audit
from app.services.access import Ctx, entry_visible_filter

router = APIRouter(tags=["evidence"])

# extension -> (kind, magic-byte check). The declared type is never trusted: content must match the extension.
def _riff(kind: bytes):
    return lambda b: b[:4] == b"RIFF" and b[8:12] == kind

ALLOWED = {
    "png": ("image", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    "jpg": ("image", lambda b: b.startswith(b"\xff\xd8\xff")),
    "jpeg": ("image", lambda b: b.startswith(b"\xff\xd8\xff")),
    "gif": ("image", lambda b: b[:4] == b"GIF8"),
    "webp": ("image", _riff(b"WEBP")),
    "pdf": ("document", lambda b: b.startswith(b"%PDF-")),
    "txt": ("text", lambda b: b"\x00" not in b),
    "mp3": ("audio", lambda b: b.startswith(b"ID3") or b[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")),
    "wav": ("audio", _riff(b"WAVE")),
    "mp4": ("video", lambda b: b[4:8] == b"ftyp"),
    "webm": ("video", lambda b: b.startswith(b"\x1aE\xdf\xa3")),
}
MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
        "txt": "text/plain", "mp3": "audio/mpeg", "wav": "audio/wav", "mp4": "video/mp4", "webm": "video/webm"}


def _store_dir() -> Path:
    p = Path(get_settings().STORAGE_DIR).resolve() / "evidence"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(item: m.EvidenceItem) -> Path:
    base = _store_dir()
    p = (base / item.stored_name).resolve()
    if base not in p.parents:  # defence in depth; stored_name is generated, never user input
        raise HTTPException(500, "Invalid storage path")
    return p


def _safe_filename(name: str) -> str:
    name = os.path.basename((name or "file").replace("\\", "/"))
    name = re.sub(r"[^\w.\- ()]", "_", name, flags=re.UNICODE).strip(" .") or "file"
    return name[:200]


def _custody(db, item_id: int, action: str, actor: m.User | None, note: str = "") -> None:
    db.add(m.EvidenceCustody(evidence_id=item_id, action=action, actor_id=actor.id if actor else None, note=note[:500]))


def _can_see_restricted(ctx: Ctx, item: m.EvidenceItem, level: str) -> bool:
    return (not item.restricted) or ctx.can("evidence.restrict") or item.uploaded_by == ctx.user.id or level == "lead"


def _get(ctx: Ctx, inv_id: int, ev_id: int, perm: str) -> tuple[m.Investigation, m.EvidenceItem, str]:
    if not ctx.can(perm):
        # still resolve the investigation first so an invisible case answers 404, not 403
        _load(ctx, inv_id)
        raise HTTPException(403, "Permission denied")
    inv, level = _load(ctx, inv_id)
    item = ctx.db.get(m.EvidenceItem, ev_id)
    if item is None or item.investigation_id != inv.id or not _can_see_restricted(ctx, item, level):
        raise NOT_FOUND
    return inv, item, level


def _row(item: m.EvidenceItem, names: dict) -> dict:
    return {"id": item.id, "investigation_id": item.investigation_id, "entry_id": item.entry_id, "title": item.title, "description": item.description,
            "kind": item.kind, "filename": item.original_filename, "mime_type": item.mime_type, "size_bytes": item.size_bytes, "sha256": item.sha256,
            "restricted": item.restricted, "is_archived": item.is_archived, "uploaded_by": names.get(item.uploaded_by), "created_at": item.created_at}


@router.get("/investigations/{inv_id}/evidence")
def list_evidence(inv_id: int, include_archived: bool = False, ctx: Ctx = Depends(get_ctx)):
    inv, level = _load(ctx, inv_id)
    if not ctx.can("evidence.read"):
        raise HTTPException(403, "Permission denied")
    q = select(m.EvidenceItem).where(m.EvidenceItem.investigation_id == inv.id)
    if not include_archived:
        q = q.where(m.EvidenceItem.is_archived.is_(False))
    items = [i for i in ctx.db.scalars(q.order_by(m.EvidenceItem.id)) if _can_see_restricted(ctx, i, level)]
    names = {u.id: u.display_name for u in ctx.db.scalars(select(m.User).where(m.User.id.in_({i.uploaded_by for i in items if i.uploaded_by})))} if items else {}
    return [_row(i, names) for i in items]


@router.post("/investigations/{inv_id}/evidence", status_code=201)
def upload_evidence(inv_id: int, file: UploadFile = File(...), title: str = Form(..., min_length=1, max_length=255), description: str = Form("", max_length=5000),
                    restricted: bool = Form(False), entry_id: int | None = Form(None), ctx: Ctx = Depends(get_ctx)):
    inv, level = _load(ctx, inv_id, "write")
    if not ctx.can("evidence.upload"):
        raise HTTPException(403, "Permission denied")
    if restricted and not ctx.can("evidence.restrict"):
        raise HTTPException(403, "You may not mark evidence as restricted")
    if inv.is_archived:
        raise HTTPException(409, "This investigation is archived")
    filename = _safe_filename(file.filename or "")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED:
        raise HTTPException(422, "File type not allowed. Allowed: " + ", ".join(sorted(ALLOWED)))
    kind, sniff = ALLOWED[ext]
    if entry_id is not None:
        ok = ctx.db.scalar(select(m.InvestigationEntry.id).where(m.InvestigationEntry.id == entry_id, m.InvestigationEntry.investigation_id == inv.id, entry_visible_filter(ctx, level)))
        if ok is None:
            raise HTTPException(422, "Unknown timeline entry")
    limit = get_settings().MAX_UPLOAD_MB * 1024 * 1024
    stored = uuid.uuid4().hex
    dest = _store_dir() / stored
    h, size, head = hashlib.sha256(), 0, b""
    try:
        with open(dest, "wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"File exceeds {get_settings().MAX_UPLOAD_MB} MB")
                if len(head) < 16:
                    head += chunk[: 16 - len(head)]
                h.update(chunk)
                out.write(chunk)
        if size == 0:
            raise HTTPException(422, "Empty file")
        sample = head
        if ext == "txt":
            with open(dest, "rb") as f:
                sample = f.read(65536)
        if not sniff(sample):
            raise HTTPException(422, "File content does not match its extension")
    except Exception:
        dest.unlink(missing_ok=True)  # never leave a rejected upload on disk
        raise
    item = m.EvidenceItem(investigation_id=inv.id, entry_id=entry_id, title=clean_text(title, 255), description=clean_text(description, 5000, multiline=True),
                          kind=kind, original_filename=filename, stored_name=stored, mime_type=MIME[ext], size_bytes=size, sha256=h.hexdigest(),
                          restricted=restricted, uploaded_by=ctx.user.id)
    ctx.db.add(item)
    ctx.db.flush()
    _custody(ctx.db, item.id, "uploaded", ctx.user, f"sha256={item.sha256}")
    audit.record(ctx.db, ctx.user, "evidence.upload", "evidence", item.id, detail={"kind": kind, "size": size, "restricted": restricted}, investigation_id=inv.id)
    ctx.db.commit()
    return _row(item, {ctx.user.id: ctx.user.display_name})


@router.get("/investigations/{inv_id}/evidence/{ev_id}/download")
def download(inv_id: int, ev_id: int, ctx: Ctx = Depends(get_ctx)):
    inv, item, _ = _get(ctx, inv_id, ev_id, "evidence.download")
    p = _path(item)
    if not p.exists():
        raise HTTPException(410, "The stored file is missing. This has been recorded.")
    _custody(ctx.db, item.id, "downloaded", ctx.user)
    audit.record(ctx.db, ctx.user, "evidence.download", "evidence", item.id, investigation_id=inv.id)
    ctx.db.commit()
    # always an attachment with a neutral type: an uploaded file can never run as a page in our origin
    return FileResponse(p, media_type="application/octet-stream", filename=item.original_filename, content_disposition_type="attachment")


@router.post("/investigations/{inv_id}/evidence/{ev_id}/verify")
def verify_integrity(inv_id: int, ev_id: int, ctx: Ctx = Depends(get_ctx)):
    inv, item, _ = _get(ctx, inv_id, ev_id, "evidence.download")
    p = _path(item)
    ok = False
    if p.exists():
        h = hashlib.sha256()
        with open(p, "rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        ok = h.hexdigest() == item.sha256
    _custody(ctx.db, item.id, "integrity_ok" if ok else "integrity_failed", ctx.user)
    audit.record(ctx.db, ctx.user, "evidence.verify", "evidence", item.id, detail={"ok": ok}, investigation_id=inv.id)
    ctx.db.commit()
    return {"ok": ok, "sha256": item.sha256}


class RestrictIn(BaseModel):
    restricted: bool
    note: str = Field(default="", max_length=500)


@router.put("/investigations/{inv_id}/evidence/{ev_id}/restriction")
def set_restriction(inv_id: int, ev_id: int, data: RestrictIn, ctx: Ctx = Depends(get_ctx)):
    inv, item, level = _get(ctx, inv_id, ev_id, "evidence.restrict")
    if level == "read":
        raise HTTPException(403, "Permission denied")
    if item.restricted != data.restricted:
        item.restricted = data.restricted
        _custody(ctx.db, item.id, "restricted" if data.restricted else "unrestricted", ctx.user, data.note)
        audit.record(ctx.db, ctx.user, "evidence.restrict", "evidence", item.id, detail={"restricted": data.restricted}, investigation_id=inv.id)
        ctx.db.commit()
    return {"ok": True}


class ArchiveIn(BaseModel):
    archived: bool
    note: str = Field(min_length=3, max_length=500)


@router.put("/investigations/{inv_id}/evidence/{ev_id}/archive")
def archive(inv_id: int, ev_id: int, data: ArchiveIn, ctx: Ctx = Depends(get_ctx)):
    inv, item, level = _get(ctx, inv_id, ev_id, "evidence.restrict")
    if level == "read":
        raise HTTPException(403, "Permission denied")
    item.is_archived = data.archived
    _custody(ctx.db, item.id, "archived" if data.archived else "restored", ctx.user, data.note)
    audit.record(ctx.db, ctx.user, "evidence.archive", "evidence", item.id, detail={"archived": data.archived}, investigation_id=inv.id)
    ctx.db.commit()
    return {"ok": True}


@router.get("/investigations/{inv_id}/evidence/{ev_id}/custody")
def custody_log(inv_id: int, ev_id: int, ctx: Ctx = Depends(get_ctx)):
    _, item, _ = _get(ctx, inv_id, ev_id, "evidence.read")
    rows = list(ctx.db.scalars(select(m.EvidenceCustody).where(m.EvidenceCustody.evidence_id == item.id).order_by(m.EvidenceCustody.id)))
    names = {u.id: u.display_name for u in ctx.db.scalars(select(m.User).where(m.User.id.in_({r.actor_id for r in rows if r.actor_id})))} if rows else {}
    return [{"action": r.action, "actor": names.get(r.actor_id), "note": r.note, "at": r.at} for r in rows]
