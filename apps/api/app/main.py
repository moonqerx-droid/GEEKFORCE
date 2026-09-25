from fastapi import FastAPI

from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router
from app.api.routes.operator import router as operator_router

app = FastAPI(title="GEEKFORCE HelpFlow API", version="0.1.0")
app.include_router(health_router)
app.include_router(conversations_router)
app.include_router(operator_router)
