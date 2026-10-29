"""Module registry (architecture.md §8, difference 2) and the panel's copy of the permission
catalog, which had no test before."""

import re
from pathlib import Path

from app.core.modules import (
    api_routers,
    installed_modules,
    managed_schemas,
    permission_codes,
)
from app.modules.identity.permissions import Perm

PANEL_PERMISSIONS = Path(__file__).parents[3] / "frontend/src/lib/auth/permissions.ts"


def test_core_modules_are_discovered_in_order() -> None:
    assert [spec.name for spec in installed_modules()] == [
        "identity",
        "audit",
        "geography",
        "people",
        "candidacies",
        "peace_movement",
    ]
    assert managed_schemas() == {
        "identity",
        "geography",
        "people",
        "candidacies",
        "peace_movement",
    }


def test_routers_cover_the_whole_api() -> None:
    prefixes = {router.prefix for router in api_routers()}
    assert {"/auth", "/users", "/audit-log", "/geography", "/people"} <= prefixes
    assert len(api_routers()) == 8  # identity has three routers


def test_permission_codes_follow_the_convention() -> None:
    codes = permission_codes()
    assert set(Perm) <= codes
    assert all(re.fullmatch(r"[a-z_]+(\.[a-z_]+){1,2}", code) for code in codes)


def test_panel_copy_matches_the_backend_catalog() -> None:
    source = PANEL_PERMISSIONS.read_text(encoding="utf-8")
    block = source[source.index("export const Perm = {") : source.index("} as const;")]
    panel = set(re.findall(r':\s*"([^"]+)"', block))
    assert panel == set(permission_codes()), (
        f"Falta en el panel: {sorted(permission_codes() - panel)}; "
        f"sobra en el panel: {sorted(panel - permission_codes())}"
    )
