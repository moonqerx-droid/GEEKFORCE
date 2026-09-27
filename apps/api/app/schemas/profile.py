from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.admin_users import normalize_full_name
from app.schemas.auth import Department, UserRole


class ProfileRead(BaseModel):
    id: str
    name: str
    email: str
    department: Department
    role: UserRole
    is_active: bool
    must_change_password: bool
    revision: int
    created_at: datetime
    last_login_at: datetime | None


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=101)
    department: Department | None = None

    _name = field_validator("full_name")(
        lambda value: normalize_full_name(value) if value is not None else value
    )


class PersonalOperatorMetrics(BaseModel):
    days: int
    resolved: int
    in_progress: int
    waiting_first_reply: int
    median_first_reply_minutes: float | None
    median_resolution_minutes: float | None
    average_rating: float | None
    ratings_count: int


class MetricDay(BaseModel):
    date: str
    resolved: int


class MetricTopic(BaseModel):
    name: str
    count: int


class FullOperatorMetrics(PersonalOperatorMetrics):
    operator_id: str
    operator_name: str
    assigned: int
    p90_first_reply_minutes: float | None
    p90_resolution_minutes: float | None
    first_reply_sla_rate: float | None
    daily: list[MetricDay]
    topics: list[MetricTopic]
    urgency: dict[str, int]
