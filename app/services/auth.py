import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, conflict, forbidden, unauthorized
from app.core.security import (burn_password_check, create_access_token, hash_password_async, hash_token,
                               needs_rehash, new_opaque_token, verify_password_async)
from app.models import Invitation, Membership, RefreshToken, User
from app.services import audit
from app.services.organizations import create_organization, list_user_organizations


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _issue_tokens(session: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID,
                        family_id: uuid.UUID | None = None) -> tuple[dict, RefreshToken]:
    raw, digest = new_opaque_token()
    row = RefreshToken(user_id=user_id, organization_id=org_id, family_id=family_id or uuid.uuid4(),
                       token_hash=digest, expires_at=_now() + timedelta(days=get_settings().refresh_token_days))
    session.add(row)
    await session.flush()
    access, ttl = create_access_token(user_id, org_id)
    return {"access_token": access, "refresh_token": raw, "token_type": "bearer",
            "expires_in": ttl, "organization_id": org_id}, row


async def register(session: AsyncSession, *, email: str, password: str, full_name: str,
                   organization_name: str, ip: str | None) -> dict:
    if not get_settings().allow_registration:
        raise forbidden("Registration is disabled", "registration_disabled")
    user = User(email=email, password_hash=await hash_password_async(password), full_name=full_name)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise conflict("An account with this email already exists", "email_taken") from None
    org, _, _ = await create_organization(session, user, organization_name)
    audit.record(session, org_id=org.id, actor=user, action="org.create", entity_type="organization",
                 entity_id=org.id, detail={"name": org.name}, ip=ip)
    tokens, _ = await _issue_tokens(session, user.id, org.id)
    memberships = await list_user_organizations(session, user.id)
    await session.commit()
    return {**tokens, "user": user, "memberships": memberships}


async def login(session: AsyncSession, *, email: str, password: str, organization_id: uuid.UUID | None,
                ip: str | None) -> dict:
    s = get_settings()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        await burn_password_check(password)
        raise unauthorized("Invalid email or password", "invalid_credentials")
    if user.locked_until and user.locked_until > _now():
        raise AppError(429, "account_locked", "Too many failed attempts. Try again later.")
    if not await verify_password_async(user.password_hash, password):
        attempts = (await session.execute(
            update(User).where(User.id == user.id)
            .values(failed_login_attempts=User.failed_login_attempts + 1)
            .returning(User.failed_login_attempts))).scalar_one()
        if attempts >= s.max_failed_logins:
            await session.execute(update(User).where(User.id == user.id).values(
                locked_until=_now() + timedelta(minutes=s.lockout_minutes), failed_login_attempts=0))
        await session.commit()
        raise unauthorized("Invalid email or password", "invalid_credentials")
    if not user.is_active:
        raise unauthorized("Invalid email or password", "invalid_credentials")

    memberships = await list_user_organizations(session, user.id)
    if not memberships:
        raise forbidden("This account does not belong to any organization", "no_organization")
    if organization_id is None:
        org_id = memberships[0]["organization_id"]
    elif any(m["organization_id"] == organization_id for m in memberships):
        org_id = organization_id
    else:
        raise forbidden("You are not a member of that organization", "not_a_member")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = _now()
    if needs_rehash(user.password_hash):
        user.password_hash = await hash_password_async(password)
    tokens, _ = await _issue_tokens(session, user.id, org_id)
    audit.record(session, org_id=org_id, actor=user, action="auth.login", entity_type="user",
                 entity_id=user.id, ip=ip)
    await session.commit()
    return {**tokens, "user": user, "memberships": memberships}


async def refresh(session: AsyncSession, *, raw_token: str, organization_id: uuid.UUID | None) -> dict:
    row = (await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)).with_for_update()
    )).scalar_one_or_none()
    if row is None:
        raise unauthorized("Invalid refresh token", "invalid_refresh_token")
    if row.revoked_at is not None:
        # A rotated token came back: assume theft and kill every token in the family.
        await _revoke_family(session, row.family_id)
        await session.commit()
        raise unauthorized("Refresh token was already used", "refresh_token_reused")
    if row.expires_at <= _now():
        raise unauthorized("Refresh token expired", "invalid_refresh_token")
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise unauthorized("Session is no longer valid", "session_invalid")
    org_id = organization_id or row.organization_id
    is_member = (await session.execute(select(Membership.id).where(
        Membership.user_id == user.id, Membership.organization_id == org_id))).first()
    if is_member is None:
        raise forbidden("You are not a member of that organization", "not_a_member")
    tokens, new_row = await _issue_tokens(session, user.id, org_id, family_id=row.family_id)
    row.revoked_at = _now()
    row.replaced_by_id = new_row.id
    memberships = await list_user_organizations(session, user.id)
    await session.commit()
    return {**tokens, "user": user, "memberships": memberships}


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(update(RefreshToken)
                          .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
                          .values(revoked_at=_now()))


async def logout(session: AsyncSession, raw_token: str) -> None:
    row = (await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))).scalar_one_or_none()
    if row is not None:
        await _revoke_family(session, row.family_id)
        await session.commit()


async def accept_invitation(session: AsyncSession, *, token: str, password: str, full_name: str,
                            ip: str | None) -> dict:
    inv = (await session.execute(
        select(Invitation).where(Invitation.token_hash == hash_token(token)).with_for_update()
    )).scalar_one_or_none()
    if inv is None or inv.accepted_at is not None or inv.expires_at <= _now():
        raise AppError(400, "invalid_invitation", "This invitation is invalid or has expired")
    user = (await session.execute(select(User).where(User.email == inv.email))).scalar_one_or_none()
    if user is None:
        user = User(email=inv.email, password_hash=await hash_password_async(password), full_name=full_name)
        session.add(user)
        await session.flush()
    else:
        # Existing account: the invitation proves the email, the password proves the account.
        if not await verify_password_async(user.password_hash, password) or not user.is_active:
            raise unauthorized("Invalid email or password", "invalid_credentials")
    session.add(Membership(organization_id=inv.organization_id, user_id=user.id, role_id=inv.role_id))
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise conflict("You are already a member of this organization", "already_member") from None
    inv.accepted_at = _now()
    audit.record(session, org_id=inv.organization_id, actor=user, action="member.accept",
                 entity_type="user", entity_id=user.id, detail={"role_id": str(inv.role_id)}, ip=ip)
    tokens, _ = await _issue_tokens(session, user.id, inv.organization_id)
    memberships = await list_user_organizations(session, user.id)
    await session.commit()
    return {**tokens, "user": user, "memberships": memberships}