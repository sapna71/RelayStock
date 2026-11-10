import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal

from pydantic import BaseModel


from app.core.config import get_settings
from app.db.session import get_session
from app.schemas.health import HealthOut, ReadyOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    """Liveness: the process is up. Never touches the database."""
    s = get_settings()
    return HealthOut(status="ok", service=s.app_name, environment=s.environment)


@router.get("/ready", response_model=ReadyOut, responses={503: {"model": ReadyOut}})
async def ready(session: AsyncSession = Depends(get_session)):
    """Readiness: PostgreSQL answers a trivial query. Error details stay in the logs."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "error"})
    return ReadyOut(status="ready", database="ok")


class HealthOut(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str


class ReadyOut(BaseModel):
    status: Literal["ready", "unavailable"]
    database: Literal["ok", "error"]