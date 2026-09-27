from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.api.routes.auth import require_trusted_origin
from app.core.config import get_settings
from app.db.session import get_db
from app.models.auth import User
from app.schemas.knowledge import KnowledgeDocumentDetail, KnowledgeDocumentRead
from app.services.knowledge import (
    KnowledgeDocumentNotFound,
    KnowledgeLimits,
    KnowledgeService,
    KnowledgeUploadRefused,
)

router = APIRouter(
    prefix="/api/admin/knowledge",
    tags=["admin", "knowledge"],
    dependencies=[Depends(require_trusted_origin)],
)

AdminDependency = Annotated[User, Depends(require_admin)]


def get_knowledge_service(db: Annotated[Session, Depends(get_db)]) -> KnowledgeService:
    return KnowledgeService(db, KnowledgeLimits.from_settings(get_settings()))


ServiceDependency = Annotated[KnowledgeService, Depends(get_knowledge_service)]


def _not_found(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Документ не найден")


@router.get("/documents", response_model=list[KnowledgeDocumentRead])
def list_documents(service: ServiceDependency, _admin: AdminDependency):
    return service.list_documents()


@router.post("/documents", response_model=KnowledgeDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    service: ServiceDependency,
    admin: AdminDependency,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=200)] = None,
    knowledge_service: Annotated[str | None, Form(alias="service", max_length=120)] = None,
    sha256: Annotated[str | None, Form(max_length=64)] = None,
):
    # Read one byte past the limit: enough to tell an oversized file without holding all of it.
    content = await file.read(service.limits.max_upload_bytes + 1)
    try:
        return service.upload(
            file.filename or "", content, file.content_type, admin,
            title=title, service=knowledge_service, checksum=sha256,
        )
    except KnowledgeUploadRefused as error:
        detail = {"message": error.message, "document_id": error.document_id} if error.document_id else error.message
        raise HTTPException(status_code=error.status_code, detail=detail) from error


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentDetail)
def get_document(document_id: str, service: ServiceDependency, _admin: AdminDependency):
    try:
        return service.get(document_id)
    except KnowledgeDocumentNotFound as error:
        raise _not_found(error) from error


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, service: ServiceDependency, admin: AdminDependency) -> Response:
    try:
        service.delete(document_id, admin)
    except KnowledgeDocumentNotFound as error:
        raise _not_found(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
