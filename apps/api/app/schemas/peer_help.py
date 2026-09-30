from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.auth import User


class ColleagueRead(BaseModel):
    id: str
    name: str
    department: str
    helped_count: int

    @classmethod
    def from_user(cls, user: User) -> "ColleagueRead":
        return cls(id=user.id, name=user.full_name, department=user.department, helped_count=user.helped_count or 0)


class PeerHelpMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class PeerHelpMessageRead(BaseModel):
    id: int
    sender: ColleagueRead
    content: str
    created_at: datetime


class PeerHelpRead(BaseModel):
    id: str
    conversation_id: str
    title: str
    area: str
    status: Literal["OPEN", "HELPING", "RESOLVED", "CANCELLED"]
    author: ColleagueRead
    helper: ColleagueRead | None
    messages: list[PeerHelpMessageRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, item, include_messages: bool = True) -> "PeerHelpRead":
        return cls(
            id=item.id, conversation_id=item.conversation_id, title=item.title, area=item.area,
            status=item.status, author=ColleagueRead.from_user(item.author),
            helper=ColleagueRead.from_user(item.helper) if item.helper else None,
            messages=[
                PeerHelpMessageRead(id=m.id, sender=ColleagueRead.from_user(m.sender),
                                    content=m.content, created_at=m.created_at)
                for m in item.messages
            ] if include_messages else [],
            created_at=item.created_at, updated_at=item.updated_at,
        )


class DirectMessageRead(BaseModel):
    id: int
    sender: ColleagueRead
    recipient: ColleagueRead
    content: str
    created_at: datetime

    @classmethod
    def from_model(cls, message) -> "DirectMessageRead":
        return cls(id=message.id, sender=ColleagueRead.from_user(message.sender),
                   recipient=ColleagueRead.from_user(message.recipient),
                   content=message.content, created_at=message.created_at)
