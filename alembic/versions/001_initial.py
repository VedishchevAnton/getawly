"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-03-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "owners",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("bot_token", sa.String(128), nullable=True),
        sa.Column("bot_username", sa.String(64), nullable=True),
        sa.Column("webhook_secret", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("bot_token"),
        sa.UniqueConstraint("webhook_secret"),
    )
    op.create_index("ix_owners_email", "owners", ["email"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("owners.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("trial", "active", "expired", "cancelled", name="subscription_status"),
            nullable=False,
            server_default="trial",
        ),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("owner_id"),
    )

    op.create_table(
        "units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("owners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("price_per_night", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_units_owner_id", "units", ["owner_id"])

    op.create_table(
        "unit_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_unit_photos_unit_id", "unit_photos", ["unit_id"])

    op.create_table(
        "blocked_dates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.UniqueConstraint("unit_id", "day", name="uq_unit_day"),
    )
    op.create_index("ix_blocked_dates_unit_id", "blocked_dates", ["unit_id"])

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("owners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("guest_name", sa.String(120), nullable=False),
        sa.Column("guest_phone", sa.String(32), nullable=False),
        sa.Column("guest_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("check_in", sa.Date(), nullable=False),
        sa.Column("check_out", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("new", "confirmed", "declined", "cancelled", name="booking_status"),
            nullable=False,
            server_default="new",
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_bookings_owner_id", "bookings", ["owner_id"])
    op.create_index("ix_bookings_unit_id", "bookings", ["unit_id"])


def downgrade() -> None:
    op.drop_table("bookings")
    op.drop_table("blocked_dates")
    op.drop_table("unit_photos")
    op.drop_table("units")
    op.drop_table("subscriptions")
    op.drop_table("owners")
    op.execute("DROP TYPE IF EXISTS booking_status")
    op.execute("DROP TYPE IF EXISTS subscription_status")
