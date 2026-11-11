from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require
from app.core.permissions import Permission
from app.db.session import get_session
from app.schemas.auth import MembershipOut
from app.schemas.org import OrgCreateIn, OrgOut, OrgUpdateIn
from app.services import organizations as svc

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.get("", response_model=list[MembershipOut])
async def my_organizations(ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_session)):
    return await svc.list_user_organizations(session, ctx.user.id)


@router.post("", response_model=OrgOut, status_code=201)
async def create_organization(body: OrgCreateIn, ctx: AuthContext = Depends(get_auth_context),
                              session: AsyncSession = Depends(get_session)):
    """Creates another organization with the caller as Director. Switch to it via POST /auth/refresh."""
    return await svc.create_for_user(session, ctx, body.name, body.timezone, body.currency)


@router.get("/current", response_model=OrgOut)
async def current(ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_session)):
    return await svc.get_current(session, ctx.org_id)


@router.patch("/current", response_model=OrgOut)
async def update_current(body: OrgUpdateIn, ctx: AuthContext = Depends(require(Permission.SETTINGS_EDIT)),
                         session: AsyncSession = Depends(get_session)):
    return await svc.update_current(session, ctx, body.model_dump(exclude_none=True))