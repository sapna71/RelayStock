"""Model registry: import every model module so Alembic autogenerate sees the tables."""
from app.models.audit import AuditLog
from app.models.organization import Organization
from app.models.rbac import Invitation, Membership, Role, RolePermission
from app.models.token import RefreshToken
from app.models.user import User

__all__ = ["AuditLog", "Invitation", "Membership", "Organization", "RefreshToken", "Role", "RolePermission", "User"]