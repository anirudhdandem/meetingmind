"""add call_metrics: talk-time split + confidence/answer-quality/conversion

Revision ID: 0008_call_metrics
Revises: 0007_transcript_role
Create Date: 2026-07-02

Phases 2-4 of performance metrics. One row per call: deterministic talk-time split
(team/client/unknown seconds + turns + our talk ratio) plus LLM-derived confidence,
answer quality, and conversion probability.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_call_metrics"
down_revision = "0007_transcript_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "call_metrics",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "call_id", sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("team_talk_seconds", sa.Float(), nullable=True),
        sa.Column("client_talk_seconds", sa.Float(), nullable=True),
        sa.Column("unknown_talk_seconds", sa.Float(), nullable=True),
        sa.Column("team_turns", sa.Integer(), nullable=True),
        sa.Column("client_turns", sa.Integer(), nullable=True),
        sa.Column("talk_ratio", sa.Float(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("confidence_notes", sa.Text(), nullable=True),
        sa.Column("answer_quality_score", sa.Integer(), nullable=True),
        sa.Column("answer_notes", sa.Text(), nullable=True),
        sa.Column("client_questions", sa.Integer(), nullable=True),
        sa.Column("questions_answered", sa.Integer(), nullable=True),
        sa.Column("conversion_probability", sa.Integer(), nullable=True),
        sa.Column("conversion_notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_call_metrics_call_id", "call_metrics", ["call_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_call_metrics_call_id", table_name="call_metrics")
    op.drop_table("call_metrics")
