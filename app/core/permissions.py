from dataclasses import dataclass
from enum import StrEnum


class Permission(StrEnum):
    INVENTORY_VIEW = "inventory.view"
    INVENTORY_ADJUST = "inventory.adjust"
    ORDERS_MANAGE = "orders.manage"
    PROCUREMENT_APPROVE = "procurement.approve"
    TRANSFERS_MANAGE = "transfers.manage"
    ANALYTICS_VIEW = "analytics.view"
    TEAM_MANAGE = "team.manage"
    SETTINGS_EDIT = "settings.edit"
    AUDIT_VIEW = "audit.view"


ALL_PERMISSIONS: frozenset[str] = frozenset(p.value for p in Permission)

PERMISSION_LABELS = {
    Permission.INVENTORY_VIEW: "View inventory",
    Permission.INVENTORY_ADJUST: "Adjust inventory",
    Permission.ORDERS_MANAGE: "Manage orders",
    Permission.PROCUREMENT_APPROVE: "Approve purchase orders",
    Permission.TRANSFERS_MANAGE: "Manage transfers",
    Permission.ANALYTICS_VIEW: "View analytics",
    Permission.TEAM_MANAGE: "Manage team",
    Permission.SETTINGS_EDIT: "Edit settings",
    Permission.AUDIT_VIEW: "View audit logs",
}


@dataclass(frozen=True)
class RoleSpec:
    name: str
    description: str
    is_owner: bool
    permissions: tuple[Permission, ...]


# Mirrors the frontend's permission matrix. The owner role holds every permission,
# including ones added in later phases, so its permissions are never stored as rows.
DEFAULT_ROLES: tuple[RoleSpec, ...] = (
    RoleSpec("Operations Director", "Full access to the organization", True, ()),
    RoleSpec("Warehouse Manager", "Runs warehouse operations", False, (
        Permission.INVENTORY_VIEW, Permission.INVENTORY_ADJUST, Permission.ORDERS_MANAGE,
        Permission.TRANSFERS_MANAGE, Permission.ANALYTICS_VIEW)),
    RoleSpec("Procurement Lead", "Owns suppliers and purchasing", False, (
        Permission.INVENTORY_VIEW, Permission.PROCUREMENT_APPROVE, Permission.ANALYTICS_VIEW)),
    RoleSpec("Inventory Analyst", "Monitors and corrects stock", False, (
        Permission.INVENTORY_VIEW, Permission.INVENTORY_ADJUST, Permission.ANALYTICS_VIEW)),
)