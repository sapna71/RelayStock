"""Baseline: required PostgreSQL extensions.

Revision ID: 0001
Revises:
Create Date: 2026-11-09
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # gen_random_uuid(), crypto helpers
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")  # case-insensitive emails and SKUs


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS citext")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")