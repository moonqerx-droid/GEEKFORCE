from pathlib import Path

from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router
from app.api.routes.operator import router as operator_router

app = FastAPI(title="GEEKFORCE HelpFlow API", version="0.1.0")
base_dir = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=base_dir / "templates")
app.mount("/static", StaticFiles(directory=base_dir / "static"), name="static")
app.include_router(health_router)
app.include_router(conversations_router)
app.include_router(operator_router)


@app.get("/debug", include_in_schema=False)
def debug_page(request: Request):
    return templates.TemplateResponse(request=request, name="debug.html")
