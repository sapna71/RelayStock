import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext
from app.core.errors import not_found
from app.core.permissions import DEFAULT_ROLES
from app.models import Membership, Organization, Role, RolePermission, User
from app.services import audit


async def create_organization(session: AsyncSession, owner: User, name: str, timezone: str = "UTC",
                              currency: str = "USD") -> tuple[Organization, Role, Membership]:
    """Create an org with the default roles and make `owner` its Director. Caller commits."""
    org = Organization(name=name, timezone=timezone, currency=currency)
    session.add(org)
    await session.flush()
    owner_role: Role | None = None
    for spec in DEFAULT_ROLES:
        role = Role(organization_id=org.id, name=spec.name, description=spec.description, is_owner=spec.is_owner)
        session.add(role)
        await session.flush()
        session.add_all(RolePermission(role_id=role.id, permission=p.value) for p in spec.permissions)
        if spec.is_owner:
            owner_role = role
    assert owner_role is not None
    membership = Membership(organization_id=org.id, user_id=owner.id, role_id=owner_role.id)
    session.add(membership)
    await session.flush()
    return org, owner_role, membership


async def list_user_organizations(session: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    rows = (await session.execute(
        select(Membership.organization_id, Organization.name, Role.id, Role.name)
        .join(Organization, Organization.id == Membership.organization_id)
        .join(Role, Role.id == Membership.role_id)
        .where(Membership.user_id == user_id).order_by(Membership.created_at))).all()
    return [{"organization_id": o, "organization_name": on, "role_id": r, "role_name": rn} for o, on, r, rn in rows]


async def create_for_user(session: AsyncSession, ctx: AuthContext, name: str, timezone: str, currency: str) -> Organization:
    org, _, _ = await create_organization(session, ctx.user, name, timezone, currency)
    audit.record(session, org_id=org.id, actor=ctx.user, action="org.create", entity_type="organization",
                 entity_id=org.id, detail={"name": name}, ip=ctx.ip)
    await session.commit()
    return org


async def get_current(session: AsyncSession, org_id: uuid.UUID) -> Organization:
    org = await session.get(Organization, org_id)
    if org is None:
        raise not_found("Organization not found")
    return org


async def update_current(session: AsyncSession, ctx: AuthContext, changes: dict) -> Organization:
    org = (await session.execute(select(Organization).where(Organization.id == ctx.org_id).with_for_update())).scalar_one()
    diff = {k: {"from": getattr(org, k), "to": v} for k, v in changes.items() if getattr(org, k) != v}
    for k in diff:
        setattr(org, k, changes[k])
    if diff:
        audit.record(session, org_id=org.id, actor=ctx.user, action="org.update", entity_type="organization",
                     entity_id=org.id, detail=diff, ip=ctx.ip)
    await session.commit()
    return org