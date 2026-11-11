import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require
from app.core.permissions import PERMISSION_LABELS, Permission
from app.db.session import get_session
from app.schemas.members import PermissionOut, RoleOut, SetPermissionsIn
from app.services import roles as svc

router = APIRouter(tags=["roles"])


@router.get("/permissions", response_model=list[PermissionOut])
async def permission_catalog(_: AuthContext = Depends(get_auth_context)):
    return [{"code": p.value, "label": label} for p, label in PERMISSION_LABELS.items()]


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_session)):
    return await svc.list_roles(session, ctx.org_id)


@router.put("/roles/{role_id}/permissions", response_model=RoleOut)
async def set_permissions(role_id: uuid.UUID, body: SetPermissionsIn,
                          ctx: AuthContext = Depends(require(Permission.TEAM_MANAGE)),
                          session: AsyncSession = Depends(get_session)):
    return await svc.set_permissions(session, ctx, role_id, body.permissions)