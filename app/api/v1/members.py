import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require
from app.core.permissions import Permission
from app.db.session import get_session
from app.schemas.members import ChangeRoleIn, InvitationOut, InviteIn, MemberOut
from app.services import members as svc

router = APIRouter(prefix="/members", tags=["members"])


@router.get("", response_model=list[MemberOut])
async def list_members(ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_session)):
    return await svc.list_members(session, ctx.org_id)


@router.post("/invitations", response_model=InvitationOut, status_code=201)
async def invite(body: InviteIn, ctx: AuthContext = Depends(require(Permission.TEAM_MANAGE)),
                 session: AsyncSession = Depends(get_session)):
    inv, raw = await svc.invite(session, ctx, email=body.email, role_id=body.role_id)
    return {"id": inv.id, "email": inv.email, "role_id": inv.role_id, "expires_at": inv.expires_at, "token": raw}


@router.patch("/{membership_id}", response_model=MemberOut)
async def change_role(membership_id: uuid.UUID, body: ChangeRoleIn,
                      ctx: AuthContext = Depends(require(Permission.TEAM_MANAGE)),
                      session: AsyncSession = Depends(get_session)):
    return await svc.change_role(session, ctx, membership_id, body.role_id)


@router.delete("/{membership_id}", status_code=204)
async def remove_member(membership_id: uuid.UUID, ctx: AuthContext = Depends(require(Permission.TEAM_MANAGE)),
                        session: AsyncSession = Depends(get_session)):
    await svc.remove_member(session, ctx, membership_id)
    return Response(status_code=204)