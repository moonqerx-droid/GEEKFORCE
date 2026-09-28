from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

MAX_TITLE = 120
MAX_BODY = 4000


def _clean(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("must not be blank")
    if len(cleaned) > limit:
        raise ValueError(f"must be at most {limit} characters")
    return cleaned


class ReplyTemplateCreate(BaseModel):
    title: str
    body: str

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _clean(value, MAX_TITLE)

    @field_validator("body")
    @classmethod
    def _body(cls, value: str) -> str:
        return _clean(value, MAX_BODY)


class ReplyTemplateUpdate(BaseModel):
    title: str | None = None
    body: str | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return _clean(value, MAX_TITLE)

    @field_validator("body")
    @classmethod
    def _body(cls, value: str | None) -> str | None:
        return _clean(value, MAX_BODY)


class ReplyTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    body: str
    created_at: datetime
    updated_at: datetime
