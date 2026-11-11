import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Email = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=254,
                                         pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class RegisterIn(BaseModel):
    email: Email
    password: Password
    full_name: Name
    organization_name: Name


class LoginIn(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)
    organization_id: uuid.UUID | None = None


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)
    organization_id: uuid.UUID | None = None


class LogoutIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class AcceptInvitationIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: Password
    full_name: Name


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    full_name: str


class MembershipOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    role_id: uuid.UUID
    role_name: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    organization_id: uuid.UUID


class AuthOut(TokenOut):
    user: UserOut
    memberships: list[MembershipOut]