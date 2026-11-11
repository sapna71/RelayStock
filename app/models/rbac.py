import uuid
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index,
                        String, Text, UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Role(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(CITEXT, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    is_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        UniqueConstraint("organization_id", "id"),  # target for tenant-safe composite foreign keys
        UniqueConstraint("organization_id", "name"),
        CheckConstraint("char_length(name::text) BETWEEN 1 AND 80", name="name_length"),
        Index("uq_roles_one_owner_per_org", "organization_id", unique=True, postgresql_where=text("is_owner")),
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission: Mapped[str] = mapped_column(String(64), primary_key=True)

    __table_args__ = (CheckConstraint("permission ~ '^[a-z_]+[.][a-z_]+$'", name="permission_format"),)


class Membership(UUIDPKMixin, Base):
    __tablename__ = "memberships"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        # A membership can only point at a role of the SAME organization.
        ForeignKeyConstraint(["organization_id", "role_id"], ["roles.organization_id", "roles.id"]),
    )


class Invitation(UUIDPKMixin, Base):
    __tablename__ = "invitations"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    invited_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("token_hash"),
        ForeignKeyConstraint(["organization_id", "role_id"], ["roles.organization_id", "roles.id"]),
        Index("uq_invitations_pending_email", "organization_id", "email", unique=True,
              postgresql_where=text("accepted_at IS NULL")),
    )