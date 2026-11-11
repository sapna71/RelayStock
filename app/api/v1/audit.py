import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require
from app.core.permissions import Permission
from app.db.session import get_session
from app.schemas.audit import AuditPage
from app.services import audit as svc

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=AuditPage)
async def list_audit_logs(action: str | None = Query(None, max_length=64, description="Action prefix, e.g. member."),
                          actor_id: uuid.UUID | None = None, limit: int = Query(50, ge=1, le=200),
                          offset: int = Query(0, ge=0),
                          ctx: AuthContext = Depends(require(Permission.AUDIT_VIEW)),
                          session: AsyncSession = Depends(get_session)):
    return await svc.list_logs(session, ctx.org_id, action_prefix=action, actor_id=actor_id, limit=limit, offset=offset)