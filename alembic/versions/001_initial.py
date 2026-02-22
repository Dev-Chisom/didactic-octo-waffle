"""initial

Revision ID: 001
Revises:
Create Date: 2025-02-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("passwordHash", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ownerId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan", sa.String(50), nullable=False),
        sa.Column("creditsBalance", sa.Integer(), nullable=True),
        sa.Column("limits", postgresql.JSONB(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["ownerId"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspaceId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("userId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(["userId"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspaceId"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("monthlyPrice", sa.Float(), nullable=True),
        sa.Column("annualPrice", sa.Float(), nullable=True),
        sa.Column("limits", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "series",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspaceId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contentType", sa.String(50), nullable=False),
        sa.Column("customTopic", postgresql.JSONB(), nullable=True),
        sa.Column("scriptPreferences", postgresql.JSONB(), nullable=True),
        sa.Column("voiceLanguage", postgresql.JSONB(), nullable=True),
        sa.Column("musicSettings", postgresql.JSONB(), nullable=True),
        sa.Column("artStyle", postgresql.JSONB(), nullable=True),
        sa.Column("captionStyle", postgresql.JSONB(), nullable=True),
        sa.Column("visualEffects", postgresql.JSONB(), nullable=True),
        sa.Column("schedule", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("estimatedCreditsPerVideo", sa.Float(), nullable=True),
        sa.Column("autoPostEnabled", sa.Boolean(), nullable=True),
        sa.Column("connectedSocialAccountIds", postgresql.JSONB(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspaceId"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seriesId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("languageCode", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("promptMetadata", postgresql.JSONB(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["seriesId"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspaceId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("format", sa.String(50), nullable=True),
        sa.Column("durationSeconds", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspaceId"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "social_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspaceId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("displayName", sa.String(255), nullable=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("avatarUrl", sa.String(2048), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("accessToken", sa.Text(), nullable=True),
        sa.Column("refreshToken", sa.Text(), nullable=True),
        sa.Column("scopes", sa.String(512), nullable=True),
        sa.Column("expiresAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspaceId"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "episodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seriesId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequenceNumber", sa.Integer(), nullable=False),
        sa.Column("scheduledAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("scriptId", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("videoAssetId", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("previewUrl", sa.String(2048), nullable=True),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("creditsUsed", sa.Float(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["scriptId"], ["scripts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["seriesId"], ["series.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["videoAssetId"], ["assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("episodeId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("socialAccountId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platformPostId", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("postedAt", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["episodeId"], ["episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["socialAccountId"], ["social_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspaceId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stripeSubscriptionId", sa.String(255), nullable=True),
        sa.Column("planId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("currentPeriodStart", sa.DateTime(timezone=True), nullable=True),
        sa.Column("currentPeriodEnd", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["planId"], ["plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspaceId"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspaceId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspaceId"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("credit_transactions")
    op.drop_table("subscriptions")
    op.drop_table("posts")
    op.drop_table("episodes")
    op.drop_table("social_accounts")
    op.drop_table("assets")
    op.drop_table("scripts")
    op.drop_table("series")
    op.drop_table("plans")
    op.drop_table("members")
    op.drop_table("workspaces")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
