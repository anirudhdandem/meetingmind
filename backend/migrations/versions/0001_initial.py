"""initial schema: pgvector extension, all tables, vector index

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-16

Baseline migration. Enables the pgvector extension, then creates every table from
the SQLAlchemy metadata (keeps this in lockstep with the ORM models), then adds an
HNSW index for cosine similarity on company_memory.embedding.
"""

from alembic import op

from app.core.db import Base
import app.models  # noqa: F401  (registers tables on Base.metadata)

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind)
    op.execute(
        "CREATE INDEX IF NOT EXISTS company_memory_embedding_hnsw "
        "ON company_memory USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DROP INDEX IF EXISTS company_memory_embedding_hnsw")
    Base.metadata.drop_all(bind=bind)
