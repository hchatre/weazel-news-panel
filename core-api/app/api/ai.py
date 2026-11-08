import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app import models as m
from app.ai import context as ctxmod
from app.ai import providers
from app.api.common import NOT_FOUND
from app.api.investigations import _load
from app.config import get_settings
from app.deps import get_ctx
from app.services import audit
from app.services.access import Ctx, article_readable

router = APIRouter(prefix="/ai", tags=["ai"])
log = logging.getLogger("weazel.ai")
LABEL = "AI-generated suggestion. Not verified. A person must review it before any use."
CITE = re.compile(r"\[E(\d+)\]")


class RunIn(BaseModel):
    task: str
    subject_type: str
    subject_id: int
    language: str = Field(default="en", pattern="^(en|fr)$")
    target_language: str | None = Field(default=None, pattern="^(en|fr)$")


def _subject(ctx: Ctx, subject_type: str, subject_id: int):
    """Returns (subject, investigation level or None). Hidden records answer 404, exactly like the normal endpoints."""
    if subject_type == "article":
        art = ctx.db.get(m.Article, subject_id)
        if art is None or not article_readable(ctx, art):
            raise NOT_FOUND
        return art, None
    if subject_type == "investigation":
        return _load(ctx, subject_id)
    raise HTTPException(422, "subject_type must be article or investigation")


def _row(r: m.AiRun) -> dict:
    return {"id": r.id, "task": r.task, "subject_type": r.subject_type, "subject_id": r.subject_id, "status": r.status, "output": r.output,
            "citations": r.citations, "unsupported_citations": r.unsupported_citations, "truncated": r.truncated, "provider": r.provider,
            "model": r.model, "disposition": r.disposition, "created_at": r.created_at, "label": LABEL}


@router.get("/status")
def status(ctx: Ctx = Depends(get_ctx)):
    s = get_settings()
    p = s.AI_PROVIDER
    return {"configured": p != "none", "allowed": ctx.can("ai.use"), "provider": p if p != "none" else None,
            "tasks": {"article": sorted(ctxmod.ARTICLE_TASKS), "investigation": sorted(ctxmod.INVESTIGATION_TASKS)}, "label": LABEL}


@router.post("/run")
def run(data: RunIn, ctx: Ctx = Depends(get_ctx)):
    s = get_settings()
    if not ctx.can("ai.use"):
        raise HTTPException(403, "Permission denied")
    provider = providers.get_provider()
    if provider is None:
        raise HTTPException(503, "The AI workspace is not configured")
    valid = ctxmod.ARTICLE_TASKS if data.subject_type == "article" else ctxmod.INVESTIGATION_TASKS if data.subject_type == "investigation" else None
    if valid is None or data.task not in valid:
        raise HTTPException(422, "Unknown task for this subject")
    subject, level = _subject(ctx, data.subject_type, data.subject_id)
    since = datetime.now(timezone.utc) - timedelta(days=1)
    used = ctx.db.scalar(select(func.count()).select_from(m.AiRun).where(m.AiRun.user_id == ctx.user.id, m.AiRun.created_at >= since)) or 0
    if used >= s.AI_DAILY_LIMIT:
        raise HTTPException(429, "Daily AI limit reached")
    if data.task == "translate" and not data.target_language:
        raise HTTPException(422, "target_language is required for translation")

    prompt, allowed, truncated = ctxmod.build(ctx, data.task, data.subject_type, subject, level, s.AI_MAX_INPUT_CHARS, data.language, data.target_language)
    inv_id = subject.id if data.subject_type == "investigation" else None
    run_row = m.AiRun(user_id=ctx.user.id, task=data.task, subject_type=data.subject_type, subject_id=data.subject_id, provider=provider.name,
                      model=getattr(provider, "model", ""), input_chars=len(prompt), input_sha256=hashlib.sha256(prompt.encode()).hexdigest(), truncated=truncated)
    try:
        text = provider.complete(ctxmod.SYSTEM, prompt)
    except providers.ProviderError as e:
        log.warning("AI provider failure for run by user %s: %s", ctx.user.id, e)  # detail stays in the server log
        run_row.status = "failed"
        ctx.db.add(run_row)
        ctx.db.flush()
        audit.record(ctx.db, ctx.user, "ai.run_failed", "ai_run", run_row.id, detail={"task": data.task, "subject": data.subject_type, "subject_id": data.subject_id}, investigation_id=inv_id)
        ctx.db.commit()
        raise HTTPException(502, "The AI service could not complete the request")

    # Grounding check: any citation that does not match an entry the model was actually given is flagged and removed.
    cited = [c for c in dict.fromkeys(CITE.findall(text))]
    good = [f"E{c}" for c in cited if f"{c}" in allowed]
    bad = [f"E{c}" for c in cited if f"{c}" not in allowed] if data.subject_type == "investigation" else [f"E{c}" for c in cited]
    for b in bad:
        text = text.replace(f"[{b}]", "[unsupported citation removed]")
    run_row.output, run_row.citations, run_row.unsupported_citations = text, good, bad
    ctx.db.add(run_row)
    ctx.db.flush()
    audit.record(ctx.db, ctx.user, "ai.run", "ai_run", run_row.id, detail={"task": data.task, "subject": data.subject_type, "subject_id": data.subject_id,
                 "provider": provider.name, "input_chars": len(prompt)}, investigation_id=inv_id)  # ids and sizes only, never prompt or output text
    ctx.db.commit()
    return _row(run_row)


@router.get("/runs")
def list_runs(subject_type: str, subject_id: int, ctx: Ctx = Depends(get_ctx)):
    if not ctx.can("ai.use"):
        raise HTTPException(403, "Permission denied")
    _subject(ctx, subject_type, subject_id)  # access is re-checked now: losing access to the record also hides old suggestions about it
    rows = ctx.db.scalars(select(m.AiRun).where(m.AiRun.user_id == ctx.user.id, m.AiRun.subject_type == subject_type, m.AiRun.subject_id == subject_id)
                          .order_by(m.AiRun.id.desc()).limit(20))
    return [_row(r) for r in rows]


class DispositionIn(BaseModel):
    disposition: str = Field(pattern="^(accepted|rejected)$")


@router.put("/runs/{run_id}/disposition")
def set_disposition(run_id: int, data: DispositionIn, ctx: Ctx = Depends(get_ctx)):
    r = ctx.db.get(m.AiRun, run_id)
    if r is None or r.user_id != ctx.user.id:
        raise NOT_FOUND
    _subject(ctx, r.subject_type, r.subject_id)
    r.disposition, r.disposition_at = data.disposition, datetime.now(timezone.utc)
    audit.record(ctx.db, ctx.user, f"ai.{data.disposition}", "ai_run", r.id, detail={"task": r.task, "subject": r.subject_type, "subject_id": r.subject_id},
                 investigation_id=r.subject_id if r.subject_type == "investigation" else None)
    ctx.db.commit()
    return _row(r)
