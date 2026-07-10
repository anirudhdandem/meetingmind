"""add kind to companies

Revision ID: 0005_company_kind
Revises: 0004_mom_contributions
Create Date: 2026-06-24

Distinguishes external companies (deals apply) from internal meetings filed
under a free-text label. Existing rows default to "external".
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_company_kind"
down_revision = "0004_mom_contributions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("kind", sa.String(), nullable=False, server_default="external"),
    )


def downgrade() -> None:
    op.drop_column("companies", "kind")
