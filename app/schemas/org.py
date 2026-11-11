import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.auth import Name, UserOut, MembershipOut

Timezone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64,
                                            pattern=r"^[A-Za-z0-9_+\-/]+$")]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    timezone: str
    currency: str
    fiscal_year_start_month: int


class OrgCreateIn(BaseModel):
    name: Name
    timezone: Timezone = "UTC"
    currency: Currency = "USD"


class OrgUpdateIn(BaseModel):
    name: Name | None = None
    timezone: Timezone | None = None
    currency: Currency | None = None
    fiscal_year_start_month: int | None = Field(default=None, ge=1, le=12)

    @model_validator(mode="after")
    def _at_least_one(self):
        if not self.model_dump(exclude_none=True):
            raise ValueError("Provide at least one field to update")
        return self


class RoleRefOut(BaseModel):
    id: uuid.UUID
    name: str
    is_owner: bool


class MeOut(BaseModel):
    user: UserOut
    organization: OrgOut
    role: RoleRefOut
    permissions: list[str]
    memberships: list[MembershipOut]