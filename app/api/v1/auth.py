from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context
from app.db.session import get_session
from app.schemas.auth import (AcceptInvitationIn, AuthOut, LoginIn, LogoutIn, RefreshIn, RegisterIn)
from app.schemas.org import MeOut
from app.services import auth as auth_service
from app.services.members import role_permission_set
from app.services.organizations import get_current, list_user_organizations

router = APIRouter(prefix="/auth", tags=["auth"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/register", response_model=AuthOut, status_code=201)
async def register(body: RegisterIn, request: Request, session: AsyncSession = Depends(get_session)):
    return await auth_service.register(session, email=body.email, password=body.password,
                                       full_name=body.full_name, organization_name=body.organization_name, ip=_ip(request))


@router.post("/login", response_model=AuthOut)
async def login(body: LoginIn, request: Request, session: AsyncSession = Depends(get_session)):
    return await auth_service.login(session, email=body.email, password=body.password,
                                    organization_id=body.organization_id, ip=_ip(request))


@router.post("/refresh", response_model=AuthOut)
async def refresh(body: RefreshIn, session: AsyncSession = Depends(get_session)):
    """Rotates the refresh token. Pass organization_id to switch the active organization."""
    return await auth_service.refresh(session, raw_token=body.refresh_token, organization_id=body.organization_id)


@router.post("/logout", status_code=204)
async def logout(body: LogoutIn, session: AsyncSession = Depends(get_session)):
    await auth_service.logout(session, body.refresh_token)
    return Response(status_code=204)


@router.post("/accept-invitation", response_model=AuthOut, status_code=201)
async def accept_invitation(body: AcceptInvitationIn, request: Request, session: AsyncSession = Depends(get_session)):
    return await auth_service.accept_invitation(session, token=body.token, password=body.password,
                                                full_name=body.full_name, ip=_ip(request))


@router.get("/me", response_model=MeOut)
async def me(ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_session)):
    return {"user": ctx.user, "organization": await get_current(session, ctx.org_id),
            "role": ctx.role, "permissions": sorted(await role_permission_set(session, ctx.role)),
            "memberships": await list_user_organizations(session, ctx.user.id)}