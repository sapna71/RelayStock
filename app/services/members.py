import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext
from app.core.config import get_settings
from app.core.errors import conflict, forbidden, not_found
from app.core.permissions import ALL_PERMISSIONS
from app.core.security import new_opaque_token
from app.models import Invitation, Membership, Role, RolePermission, User
from app.services import audit


async def role_permission_set(session: AsyncSession, role: Role) -> frozenset[str]:
    if role.is_owner:
        return ALL_PERMISSIONS
    rows = await session.execute(select(RolePermission.permission).where(RolePermission.role_id == role.id))
    return frozenset(rows.scalars())


async def get_role(session: AsyncSession, org_id: uuid.UUID, role_id: uuid.UUID) -> Role:
    role = (await session.execute(select(Role).where(Role.id == role_id, Role.organization_id == org_id))).scalar_one_or_none()
    if role is None:
        raise not_found("Role not found", "role_not_found")
    return role


async def _check_can_grant(session: AsyncSession, ctx: AuthContext, role: Role) -> None:
    """Directors may assign any role. Everyone else may only hand out what they already hold."""
    if ctx.role.is_owner:
        return
    if role.is_owner:
        raise forbidden("Only a Director can assign the Director role", "owner_only")
    if (await role_permission_set(session, role)) - ctx.permissions:
        raise forbidden("You cannot grant permissions you do not hold", "privilege_escalation")


async def _lock_owner_memberships(session: AsyncSession, org_id: uuid.UUID) -> list[uuid.UUID]:
    """Lock the org's Director memberships in a fixed order. Concurrent demotions serialize here,
    and the re-evaluated WHERE clause after the wait shows the true remaining count."""
    owner_role = select(Role.id).where(Role.organization_id == org_id, Role.is_owner).scalar_subquery()
    rows = await session.execute(select(Membership.id).where(
        Membership.organization_id == org_id, Membership.role_id == owner_role
    ).order_by(Membership.id).with_for_update())
    return list(rows.scalars())


async def list_members(session: AsyncSession, org_id: uuid.UUID) -> list[dict]:
    rows = (await session.execute(
        select(Membership, User, Role).join(User, User.id == Membership.user_id)
        .join(Role, Role.id == Membership.role_id)
        .where(Membership.organization_id == org_id).order_by(User.full_name))).all()
    return [{"id": m.id, "user_id": u.id, "email": u.email, "full_name": u.full_name, "role_id": r.id,
             "role_name": r.name, "last_login_at": u.last_login_at, "joined_at": m.created_at} for m, u, r in rows]


async def invite(session: AsyncSession, ctx: AuthContext, *, email: str, role_id: uuid.UUID) -> tuple[Invitation, str]:
    role = await get_role(session, ctx.org_id, role_id)
    await _check_can_grant(session, ctx, role)
    already = (await session.execute(
        select(Membership.id).join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.org_id, User.email == email))).first()
    if already:
        raise conflict("That person is already a member", "already_member")
    now = datetime.now(timezone.utc)
    await session.execute(delete(Invitation).where(
        Invitation.organization_id == ctx.org_id, Invitation.email == email,
        Invitation.accepted_at.is_(None), Invitation.expires_at <= now))
    raw, digest = new_opaque_token()
    inv = Invitation(organization_id=ctx.org_id, email=email, role_id=role.id, token_hash=digest,
                     invited_by_id=ctx.user.id, expires_at=now + timedelta(days=get_settings().invitation_days))
    session.add(inv)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise conflict("An invitation for this email is already pending", "invitation_pending") from None
    audit.record(session, org_id=ctx.org_id, actor=ctx.user, action="member.invite", entity_type="invitation",
                 entity_id=inv.id, detail={"email": email, "role": role.name}, ip=ctx.ip)
    await session.commit()
    return inv, raw


async def change_role(session: AsyncSession, ctx: AuthContext, membership_id: uuid.UUID, role_id: uuid.UUID) -> dict:
    owner_ids = await _lock_owner_memberships(session, ctx.org_id)
    m = (await session.execute(select(Membership).where(
        Membership.id == membership_id, Membership.organization_id == ctx.org_id).with_for_update())).scalar_one_or_none()
    if m is None:
        raise not_found("Member not found", "member_not_found")
    new_role = await get_role(session, ctx.org_id, role_id)
    current = await session.get(Role, m.role_id)
    if current.is_owner and not ctx.role.is_owner:
        raise forbidden("Only a Director can change a Director", "owner_only")
    await _check_can_grant(session, ctx, new_role)
    if current.is_owner and not new_role.is_owner and len(owner_ids) <= 1:
        raise conflict("An organization needs at least one Director", "last_owner")
    if current.id != new_role.id:
        m.role_id = new_role.id
        audit.record(session, org_id=ctx.org_id, actor=ctx.user, action="member.role_change", entity_type="membership",
                     entity_id=m.id, detail={"from": current.name, "to": new_role.name}, ip=ctx.ip)
    await session.commit()
    return next(x for x in await list_members(session, ctx.org_id) if x["id"] == m.id)


async def remove_member(session: AsyncSession, ctx: AuthContext, membership_id: uuid.UUID) -> None:
    owner_ids = await _lock_owner_memberships(session, ctx.org_id)
    m = (await session.execute(select(Membership).where(
        Membership.id == membership_id, Membership.organization_id == ctx.org_id).with_for_update())).scalar_one_or_none()
    if m is None:
        raise not_found("Member not found", "member_not_found")
    role = await session.get(Role, m.role_id)
    if role.is_owner and not ctx.role.is_owner:
        raise forbidden("Only a Director can remove a Director", "owner_only")
    if role.is_owner and len(owner_ids) <= 1:
        raise conflict("An organization needs at least one Director", "last_owner")
    user = await session.get(User, m.user_id)
    audit.record(session, org_id=ctx.org_id, actor=ctx.user, action="member.remove", entity_type="membership",
                 entity_id=m.id, detail={"email": user.email, "role": role.name}, ip=ctx.ip)
    await session.delete(m)
    await session.commit()