import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden, unauthorized
from app.core.permissions import ALL_PERMISSIONS, Permission
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import Membership, Role, RolePermission, User

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    org_id: uuid.UUID
    role: Role
    permissions: frozenset[str]
    ip: str | None


async def get_auth_context(request: Request,
                           creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                           session: AsyncSession = Depends(get_session)) -> AuthContext:
    """Authenticate the token, then load membership and permissions from the database on every
    request, so removing a member or editing a role takes effect immediately."""
    if creds is None:
        raise unauthorized()
    claims = decode_access_token(creds.credentials)
    try:
        user_id, org_id = uuid.UUID(claims["sub"]), uuid.UUID(claims["org"])
    except (KeyError, ValueError):
        raise unauthorized("Invalid or expired token", "invalid_token") from None
    row = (await session.execute(
        select(User, Role).join(Membership, Membership.user_id == User.id)
        .join(Role, Role.id == Membership.role_id)
        .where(User.id == user_id, Membership.organization_id == org_id))).first()
    if row is None or not row[0].is_active:
        raise unauthorized("Session is no longer valid", "session_invalid")
    user, role = row
    if role.is_owner:
        perms = ALL_PERMISSIONS
    else:
        perms = frozenset((await session.execute(
            select(RolePermission.permission).where(RolePermission.role_id == role.id))).scalars())
    return AuthContext(user, org_id, role, perms, request.client.host if request.client else None)


def require(*needed: Permission):
    async def dependency(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        missing = [p.value for p in needed if p.value not in ctx.permissions]
        if missing:
            raise forbidden(f"Missing permission: {', '.join(missing)}", "missing_permission")
        return ctx
    return dependency