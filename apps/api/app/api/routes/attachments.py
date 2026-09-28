from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_verified_user
from app.db.session import get_db
from app.models.auth import User
from app.services.attachments import AttachmentService

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

INLINE = {"image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf", "text/plain"}


@router.get("/{attachment_id}", response_class=Response)
def download_attachment(
    attachment_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_verified_user)],
) -> Response:
    attachment = AttachmentService(db).get_for(attachment_id, user)
    # Someone else's file answers exactly like a missing one: its existence is not revealed.
    if attachment is None or user.must_change_password:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
    disposition = "inline" if attachment.content_type in INLINE else "attachment"
    media_type = "text/plain; charset=utf-8" if attachment.content_type == "text/plain" else attachment.content_type
    return Response(
        content=attachment.data,
        media_type=media_type,
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(attachment.filename)}",
            "X-Content-Type-Options": "nosniff",
            # Even if a file were mis-sniffed, it could not run script or load anything.
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox",
            "Cache-Control": "private, max-age=3600",
        },
    )
