"""ORM model: companies — the anchor entity everything keys off."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk


class Company(Base, UUIDPk, Timestamped):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String, nullable=False)
    # Segment drives cohort comparison (won vs lost within a segment).
    segment: Mapped[str | None] = mapped_column(String, nullable=True)
    # "external" = a real company we met with (deals apply); "internal" = an internal
    # meeting filed under a free-text label so it can be found again later.
    kind: Mapped[str] = mapped_column(String, nullable=False, default="external", server_default="external")
    # Who on our team led/presented the pitch, and what product was pitched.
    # User-entered in the post-MOM save dialog (never LLM-predicted).
    presented_by: Mapped[str | None] = mapped_column(String, nullable=True)
    product_pitched: Mapped[str | None] = mapped_column(String, nullable=True)
