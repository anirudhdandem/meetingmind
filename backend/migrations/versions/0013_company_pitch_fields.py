"""companies.presented_by + product_pitched: who led the pitch and what was pitched

Revision ID: 0013_company_pitch_fields
Revises: 0012_oauth_purpose
Create Date: 2026-07-02

User-entered in the post-MOM "save meeting" dialog (deliberately not LLM-predicted),
shown as columns on the Companies page.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_company_pitch_fields"
down_revision = "0012_oauth_purpose"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("presented_by", sa.String(), nullable=True))
    op.add_column("companies", sa.Column("product_pitched", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "product_pitched")
    op.drop_column("companies", "presented_by")
