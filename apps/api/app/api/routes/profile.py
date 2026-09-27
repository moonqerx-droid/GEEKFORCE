from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_operator, require_verified_user
from app.api.routes.auth import require_trusted_origin
from app.core.config import get_settings
from app.db.session import get_db
from app.models.auth import User
from app.schemas.admin_users import normalize_full_name
from app.schemas.profile import PersonalOperatorMetrics, ProfileRead, ProfileUpdate
from app.services.operator_metrics import OperatorMetricsService
from app.services.user_admin import serialize_user, split_full_name


router = APIRouter(
    prefix="/api/profile",
    tags=["profile"],
    dependencies=[Depends(require_trusted_origin)],
)
ProfileUser = Annotated[User, Depends(require_verified_user)]
OperatorUser = Annotated[User, Depends(require_operator)]


def _profile(user: User) -> dict:
    data = serialize_user(user)
    return {key: value for key, value in data.items() if key != "status"}


@router.get("", response_model=ProfileRead)
def read_profile(user: ProfileUser):
    return _profile(user)


@router.patch("", response_model=ProfileRead)
def update_profile(payload: ProfileUpdate, user: ProfileUser, db: Annotated[Session, Depends(get_db)]):
    values = payload.model_dump(exclude_unset=True)
    if "full_name" in values:
        first_name, last_name = split_full_name(normalize_full_name(values["full_name"]))
        user.first_name, user.last_name = first_name, last_name
    if "department" in values:
        user.department = values["department"]
    if values:
        user.revision += 1
        db.commit()
        db.refresh(user)
    return _profile(user)


@router.get("/metrics", response_model=PersonalOperatorMetrics)
def personal_metrics(
    user: OperatorUser,
    db: Annotated[Session, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=90)] = 7,
):
    result = OperatorMetricsService(
        db, first_reply_sla_minutes=get_settings().support_first_reply_sla_minutes,
    ).for_operator(user.id, days)
    return result
