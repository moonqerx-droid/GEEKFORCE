from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    position: int
    text: str
    char_count: int
    token_count: int
    metadata: dict = Field(default_factory=dict, validation_alias="chunk_metadata")


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    original_filename: str
    media_type: str
    size_bytes: int
    sha256: str
    service: str | None = None
    status: Literal["processing", "ready", "failed"]
    error_message: str | None = None
    extracted_chars: int = 0
    chunk_count: int = 0
    uploaded_by: str | None = None
    uploaded_by_name: str | None = None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None = None
    revision: int


class KnowledgeDocumentDetail(KnowledgeDocumentRead):
    chunks: list[KnowledgeChunkRead] = Field(default_factory=list)
