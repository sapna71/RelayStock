from fastapi import APIRouter

from app.api.v1 import audit, auth, members, orgs, roles

api_router = APIRouter()
for module in (auth, orgs, members, roles, audit):
    api_router.include_router(module.router)