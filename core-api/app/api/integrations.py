from fastapi import APIRouter, Depends

from app.config import get_settings
from app.deps import require
from app.services.access import Ctx

router = APIRouter(prefix="/admin/integrations", tags=["integrations"])


@router.get("/status")
def status(ctx: Ctx = Depends(require("settings.manage"))):
    s = get_settings()
    # Never returns the bridge secret or any key.
    return {"bridge_configured": bool(s.BRIDGE_SECRET), "auth_mode": s.AUTH_MODE, "ai_provider": s.AI_PROVIDER}
