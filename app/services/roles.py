import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext
from app.core.errors import AppError, conflict, forbidden
from app.core.permissions import ALL_PERMISSIONS
from app.models import Membership, Role, RolePermission
from app.services import audit
from app.services.members import get_role, role_permission_set


async def list_roles(session: AsyncSession, org_id: uuid.UUID) -> list[dict]:
    roles = (await session.execute(select(Role).where(Role.organization_id == org_id)
                                   .order_by(Role.is_owner.desc(), Role.name))).scalars().all()
    perms: dict[uuid.UUID, list[str]] = {r.id: [] for r in roles}
    for rid, p in (await session.execute(select(RolePermission.role_id, RolePermission.permission)
                                         .where(RolePermission.role_id.in_(list(perms))))).all():
        perms[rid].append(p)
    counts = dict((await session.execute(select(Membership.role_id, func.count())
                                         .where(Membership.organization_id == org_id)
                                         .group_by(Membership.role_id))).all())
    return [{"id": r.id, "name": r.name, "description": r.description, "is_owner": r.is_owner,
             "permissions": sorted(ALL_PERMISSIONS if r.is_owner else perms[r.id]),
             "member_count": counts.get(r.id, 0)} for r in roles]


async def set_permissions(session: AsyncSession, ctx: AuthContext, role_id: uuid.UUID, requested: list[str]) -> dict:
    unknown = set(requested) - ALL_PERMISSIONS
    if unknown:
        raise AppError(422, "unknown_permission", f"Unknown permissions: {', '.join(sorted(unknown))}")
    role = (await session.execute(select(Role).where(Role.id == role_id, Role.organization_id == ctx.org_id)
                                  .with_for_update())).scalar_one_or_none()
    if role is None:
        raise AppError(404, "role_not_found", "Role not found")
    if role.is_owner:
        raise conflict("The Director role always has every permission", "role_locked")
    new = frozenset(requested)
    current = await role_permission_set(session, role)
    added, removed = new - current, current - new
    if not ctx.role.is_owner and (added - ctx.permissions):
        raise forbidden("You cannot grant permissions you do not hold", "privilege_escalation")
    if removed:
        await session.execute(delete(RolePermission).where(
            RolePermission.role_id == role.id, RolePermission.permission.in_(removed)))
    session.add_all(RolePermission(role_id=role.id, permission=p) for p in added)
    if added or removed:
        audit.record(session, org_id=ctx.org_id, actor=ctx.user, action="role.permissions_update",
                     entity_type="role", entity_id=role.id,
                     detail={"role": role.name, "added": sorted(added), "removed": sorted(removed)}, ip=ctx.ip)
    await session.commit()
    return next(r for r in await list_roles(session, ctx.org_id) if r["id"] == role.id)