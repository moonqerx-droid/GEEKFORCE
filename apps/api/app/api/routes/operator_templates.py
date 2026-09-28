"""Reply templates: specialists read them, only the support lead changes them."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin, require_operator
from app.api.routes.auth import require_trusted_origin
from app.db.session import get_db
from app.models.audit import AdminAuditEvent
from app.models.auth import User
from app.models.reply_template import ReplyTemplate
from app.schemas.reply_template import ReplyTemplateCreate, ReplyTemplateRead, ReplyTemplateUpdate

router = APIRouter(
    prefix="/api/operator/templates",
    tags=["operator"],
    dependencies=[Depends(require_trusted_origin)],
)

DbDependency = Annotated[Session, Depends(get_db)]
AdminDependency = Annotated[User, Depends(require_admin)]


def _get(db: Session, template_id: str) -> ReplyTemplate:
    template = db.get(ReplyTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")
    return template


def _audit(db: Session, actor: User, action: str, template: ReplyTemplate) -> None:
    db.add(AdminAuditEvent(actor_id=actor.id, action=action,
                           changes={"template_id": template.id, "title": template.title}))


@router.get("", response_model=list[ReplyTemplateRead])
def list_templates(db: DbDependency, _user: Annotated[User, Depends(require_operator)]):
    return db.scalars(select(ReplyTemplate).order_by(ReplyTemplate.title, ReplyTemplate.id)).all()


@router.post("", response_model=ReplyTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(payload: ReplyTemplateCreate, db: DbDependency, admin: AdminDependency):
    template = ReplyTemplate(title=payload.title, body=payload.body, created_by=admin.id)
    db.add(template)
    db.flush()
    _audit(db, admin, "template.created", template)
    db.commit()
    return template


@router.patch("/{template_id}", response_model=ReplyTemplateRead)
def update_template(template_id: str, payload: ReplyTemplateUpdate, db: DbDependency, admin: AdminDependency):
    template = _get(db, template_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(template, field, value)
    _audit(db, admin, "template.updated", template)
    db.commit()
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: str, db: DbDependency, admin: AdminDependency) -> Response:
    template = _get(db, template_id)
    _audit(db, admin, "template.deleted", template)
    db.delete(template)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
