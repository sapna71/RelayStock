import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.auth import Email


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role_id: uuid.UUID
    role_name: str
    last_login_at: datetime | None
    joined_at: datetime


class InviteIn(BaseModel):
    email: Email
    role_id: uuid.UUID


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role_id: uuid.UUID
    expires_at: datetime
    token: str  # shown exactly once; only its hash is stored


class ChangeRoleIn(BaseModel):
    role_id: uuid.UUID


class RoleOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    is_owner: bool
    permissions: list[str]
    member_count: int


class SetPermissionsIn(BaseModel):
    permissions: list[str]


class PermissionOut(BaseModel):
    code: str
    label: str