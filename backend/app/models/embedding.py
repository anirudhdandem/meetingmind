"""ORM model: company_memory — per-company embeddings in pgvector (spec step 7)."""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk

# gemini-embedding-001 is requested at 768 dims (output_dimensionality=768) to keep
# the pgvector index small. Keep this in sync with embeddings.embedder.EMBED_DIM.
EMBED_DIM = 768


class CompanyMemory(Base, UUIDPk, Timestamped):
    __tablename__ = "company_memory"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    call_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
