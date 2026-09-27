from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path

from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router
from app.api.routes.operator import router as operator_router
from app.db.base import Base
from app.db.session import engine
from app.core.config import get_settings
from app import models  # noqa: F401 -- registers SQLAlchemy tables


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
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
base_dir = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=base_dir / "templates")
app.mount("/static", StaticFiles(directory=base_dir / "static"), name="static")
app.include_router(health_router)
app.include_router(conversations_router)
app.include_router(operator_router)


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
