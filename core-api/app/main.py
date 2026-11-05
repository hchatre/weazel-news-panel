from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import admin, articles, auth, dashboard, investigations, public, search
from app.config import get_settings
from app.db import SessionLocal

settings = get_settings()
app = FastAPI(title="Weazel News Intelligence API", version="0.2.0", docs_url="/docs" if settings.ENVIRONMENT != "production" else None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/health", tags=["health"])
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("select 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:
        return {"status": "degraded", "database": "error"}


for r in (auth.router, articles.router, investigations.router, search.router, dashboard.router, admin.router, public.router):
    app.include_router(r, prefix="/api/v1")
