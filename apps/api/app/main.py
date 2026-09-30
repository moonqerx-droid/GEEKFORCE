from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.requests import Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router
from app.api.routes.operator import router as operator_router
from app.api.routes.operator_sla import router as operator_sla_router
from app.api.routes.operator_templates import router as operator_templates_router
from app.api.routes.auth import require_trusted_origin, router as auth_router
from app.api.routes.admin import router as admin_router
from app.api.routes.attachments import router as attachments_router
from app.api.routes.profile import router as profile_router
from app.api.routes.knowledge_admin import router as knowledge_admin_router
from app.api.routes.known_issues import router as known_issues_router
from app.api.routes.self_help import router as self_help_router
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.core.config import get_settings
from app import models  # noqa: F401 -- registers SQLAlchemy tables
from app.services.admin import bootstrap_admin
from app.api.routes.conversations import get_triage_engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    settings = get_settings()
    with SessionLocal() as session:
        bootstrap_admin(session, email=settings.admin_email, password=settings.admin_password)
    # Build the engine now: its meaning index starts embedding in the background, so the
    # first employees after a restart do not get the keywords-only path.
    get_triage_engine()
    yield


app = FastAPI(title="GEEKFORCE HelpFlow API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def add_security_headers(response: Response) -> Response:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
    )
    return response


@app.middleware("http")
async def enforce_request_security(request: Request, call_next):
    try:
        require_trusted_origin(request)
    except HTTPException as exc:
        return add_security_headers(JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}))
    return add_security_headers(await call_next(request))


base_dir = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=base_dir / "templates")
app.mount("/static", StaticFiles(directory=base_dir / "static"), name="static")
app.include_router(health_router)
app.include_router(conversations_router)
app.include_router(operator_router)
app.include_router(operator_sla_router)
app.include_router(operator_templates_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(attachments_router)
app.include_router(profile_router)
app.include_router(knowledge_admin_router)
app.include_router(known_issues_router)
app.include_router(self_help_router)


def asset_versions(*names: str) -> dict[str, str]:
    return {
        name: sha256((base_dir / "static" / name).read_bytes()).hexdigest()[:12]
        for name in names
    }


@app.get("/debug", include_in_schema=False)
def debug_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="debug.html",
        context={"assets": asset_versions("debug.css", "debug.js")},
    )


@app.get("/debug/operator", include_in_schema=False)
def operator_debug_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="operator-debug.html",
        context={"assets": asset_versions("debug.css", "operator-debug.js")},
    )
