"""replace TOTP 2FA with an emailed one-time code, and open self-serve signup

Revision ID: 0015_email_otp
Revises: 0014_auth_users
Create Date: 2026-07-10

The second factor moves from an authenticator app to a code mailed at every sign-in.
That removes the enrolment step entirely (no QR, no recovery codes), so `users` loses
its TOTP columns and `recovery_codes` goes away. The outstanding code lives on the
pending session row, next to the attempt counter that already guarded it.

Every existing session is deleted: the columns that decided whether a session was
authenticated are being renamed and re-interpreted, and the honest way to migrate a
half-finished login is to make the user do it again. Users whose authenticator was
enrolled are treated as having a verified address — they had proven the account was
theirs, just by a different means.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_email_otp"
down_revision = "0014_auth_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # An enrolled authenticator was proof the account belonged to its owner; don't make
    # those users re-prove it. (Unenrolled accounts stay unverified and, since signup
    # can re-claim them, remain recoverable.)
    op.execute("UPDATE users SET email_verified = true WHERE totp_enabled")

    op.drop_column("users", "totp_secret")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_last_step")

    op.drop_index("ix_recovery_codes_user_id", table_name="recovery_codes")
    op.drop_table("recovery_codes")

    # Nothing here can be meaningfully carried forward: a live session was one whose
    # holder had passed a TOTP check, and that factor no longer exists.
    op.execute("DELETE FROM user_sessions")

    op.alter_column("user_sessions", "mfa_pending", new_column_name="otp_pending")
    op.alter_column("user_sessions", "mfa_attempts", new_column_name="otp_attempts")
    op.add_column("user_sessions", sa.Column("otp_code_hash", sa.String(), nullable=True))
    op.add_column(
        "user_sessions", sa.Column("otp_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "user_sessions", sa.Column("otp_sent_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.execute("DELETE FROM user_sessions")

    op.drop_column("user_sessions", "otp_sent_at")
    op.drop_column("user_sessions", "otp_expires_at")
    op.drop_column("user_sessions", "otp_code_hash")
    op.alter_column("user_sessions", "otp_attempts", new_column_name="mfa_attempts")
    op.alter_column("user_sessions", "otp_pending", new_column_name="mfa_pending")

    op.create_table(
        "recovery_codes",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_recovery_codes_user_id", "recovery_codes", ["user_id"])

    # The secrets themselves are gone for good; everyone re-enrols.
    op.add_column("users", sa.Column("totp_secret", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("users", sa.Column("totp_last_step", sa.Integer(), nullable=True))
    op.drop_column("users", "email_verified")
