"""add the password-reset code columns to users

Revision ID: 0016_password_reset
Revises: 0015_email_otp
Create Date: 2026-07-10

A forgotten password is recovered with a code mailed to the account's address, the
same primitive as the sign-in code. The outstanding code hangs off `users` rather
than off a pending session, because a reset is requested by someone who is not logged
in — and a session carrying a redeemable code would be promotable to a live login by
`/auth/verify`, turning "I forgot my password" into "let me in without one".
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_password_reset"
down_revision = "0015_email_otp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("reset_code_hash", sa.String(), nullable=True))
    op.add_column(
        "users", sa.Column("reset_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("reset_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("reset_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("users", "reset_attempts")
    op.drop_column("users", "reset_sent_at")
    op.drop_column("users", "reset_expires_at")
    op.drop_column("users", "reset_code_hash")
