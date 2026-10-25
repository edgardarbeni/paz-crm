"""Geography API (D-19) and geographic scope (D-34), including what users must NOT see."""

import math
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.fixtures.bgd import X0, Y0
from tests.integration.conftest import Account, UserFactory, token_for
from tests.integration.geography.conftest import Importer, rows, scalar


async def lonlat(engine: AsyncEngine, x: float, y: float) -> tuple[float, float]:
    point = (
        await rows(
            engine,
            "SELECT ST_X(p) AS lon, ST_Y(p) AS lat FROM "
            "(SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), 32613), 4326) AS p) t",
            x=X0 + x,
            y=Y0 + y,
        )
    )[0]
    return point["lon"], point["lat"]


async def node_id(engine: AsyncEngine, table: str, where: str) -> str:
    return str(
        await scalar(engine, f"SELECT id FROM geography.{table} WHERE {where} AND is_active")
    )


@pytest.fixture
async def loaded(run_import: Importer) -> None:
    await run_import()


@pytest.fixture
async def root(make_user: UserFactory, client: AsyncClient) -> dict[str, str]:
    return await token_for(client, await make_user(roles=("superadmin",), with_totp=True))


async def _scoped_user(
    client: AsyncClient,
    make_user: UserFactory,
    root: dict[str, str],
    scopes: list[dict[str, Any]],
    *,
    roles: tuple[str, ...] = ("viewer",),
    with_totp: bool = False,
) -> tuple[Account, dict[str, str]]:
    user = await make_user(roles=roles, with_totp=with_totp)
    if scopes:
        response = await client.put(
            f"/api/v1/users/{user.id}/scopes", headers=root, json={"scopes": scopes}
        )
        assert response.status_code == 200, response.text
    return user, await token_for(client, user)


# --- unrestricted reads ----------------------------------------------------------------------


@pytest.mark.usefixtures("loaded")
async def test_list_filter_and_detail(
    client: AsyncClient, root: dict[str, str], owner_engine: AsyncEngine
) -> None:
    municipalities = (await client.get("/api/v1/geography/municipality", headers=root)).json()
    assert [(m["key"], m["name"]) for m in municipalities["items"]] == [
        ("01-001", "MUNICIPIO UNO"),
        ("01-002", "MUNICIPIO DOS"),
    ]
    municipality_one = municipalities["items"][0]["id"]
    sections = (
        await client.get(
            "/api/v1/geography/section", headers=root, params={"municipality_id": municipality_one}
        )
    ).json()
    assert [s["key"] for s in sections["items"]] == ["01-0101", "01-0102", "01-0105", "01-0106"]

    page = (await client.get("/api/v1/geography/section", headers=root, params={"limit": 3})).json()
    assert page["has_more"] is True
    rest = (
        await client.get(
            "/api/v1/geography/section",
            headers=root,
            params={"limit": 10, "cursor": page["next_cursor"]},
        )
    ).json()
    assert len(page["items"]) + len(rest["items"]) == 8

    by_name = (
        await client.get("/api/v1/geography/locality", headers=root, params={"q": "pena"})
    ).json()
    assert [item["name"] for item in by_name["items"]] == ["VILLA DE PEÑA"]

    section = await node_id(owner_engine, "sections", "section_number = 101")
    detail = (
        await client.get(
            f"/api/v1/geography/section/{section}", headers=root, params={"geometry": True}
        )
    ).json()
    assert detail["key"] == "01-0101"
    assert detail["geometry"]["type"] in {"Polygon", "MultiPolygon"}
    assert detail["block_count"] == 4  # blocks 1, 2, 5 (drawn outside) and 6 (mismatch)
    assert detail["ancestors"]["federal_district"]["key"] == "01-01"
    assert detail["ancestors"]["electoral_region"]["key"] == "C2"
    west, south, east, north = detail["bbox"]
    assert west < east
    assert south < north

    bad_filter = await client.get(
        "/api/v1/geography/state", headers=root, params={"municipality_id": section}
    )
    assert bad_filter.status_code == 400
    assert (await client.get("/api/v1/geography/planet", headers=root)).status_code == 422


@pytest.mark.usefixtures("loaded")
async def test_search_by_key_and_name(client: AsyncClient, root: dict[str, str]) -> None:
    async def keys(q: str, **extra: Any) -> list[str]:
        response = await client.get(
            "/api/v1/geography/search", headers=root, params={"q": q, **extra}
        )
        assert response.status_code == 200, response.text
        return [f"{item['level']}:{item['key']}" for item in response.json()]

    assert await keys("01-0103") == ["section:01-0103"]
    assert await keys("1 103") == ["section:01-0103"]
    assert await keys("010103") == ["section:01-0103"]
    assert await keys("01002") == ["municipality:01-002"]
    assert set(await keys("1-2")) == {
        "municipality:01-002",
        "federal_district:01-02",
        "local_district:01-02",
    }
    assert await keys("1-2", level="local_district") == ["local_district:01-02"]
    assert "neighborhood:01-COL-11" in await keys("cañadas")
    assert "locality:01-001-0001" in await keys("VILLA DE PENA")
    too_short = await client.get("/api/v1/geography/search", headers=root, params={"q": "ab"})
    assert too_short.status_code == 400


@pytest.mark.usefixtures("loaded")
async def test_locate_point(
    client: AsyncClient, root: dict[str, str], owner_engine: AsyncEngine
) -> None:
    lon, lat = await lonlat(owner_engine, 2500, 1500)  # section 107, municipality 2, DF 2, DL 1
    located = await client.get(
        "/api/v1/geography/locate", headers=root, params={"lat": lat, "lon": lon}
    )
    assert located.status_code == 200
    body = located.json()
    assert {
        name: body[name]["key"]
        for name in ("section", "municipality", "federal_district", "local_district", "state")
    } == {
        "section": "01-0107",
        "municipality": "01-002",
        "federal_district": "01-02",
        "local_district": "01-01",
        "state": "01",
    }
    outside = await client.get(
        "/api/v1/geography/locate", headers=root, params={"lat": 0, "lon": 0}
    )
    assert outside.status_code == 404


@pytest.mark.usefixtures("loaded")
async def test_vector_tiles(
    client: AsyncClient, root: dict[str, str], owner_engine: AsyncEngine
) -> None:
    lon, lat = await lonlat(owner_engine, 1000, 1000)

    def tile(z: int) -> tuple[int, int]:
        n = 2**z
        rad = math.radians(lat)
        return int((lon + 180) / 360 * n), int(
            (1 - math.log(math.tan(rad) + 1 / math.cos(rad)) / math.pi) / 2 * n
        )

    x, y = tile(14)
    response = await client.get(f"/api/v1/geography/tiles/sections/14/{x}/{y}.mvt", headers=root)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    assert len(response.content) > 50
    cached = await client.get(f"/api/v1/geography/tiles/sections/14/{x}/{y}.mvt", headers=root)
    assert cached.content == response.content

    low = await client.get("/api/v1/geography/tiles/blocks/3/1/3.mvt", headers=root)
    assert (low.status_code, low.content) == (200, b"")  # below the layer's minimum zoom
    assert (
        await client.get(f"/api/v1/geography/tiles/rivers/14/{x}/{y}.mvt", headers=root)
    ).status_code == 404
    assert (
        await client.get("/api/v1/geography/tiles/sections/2/9/9.mvt", headers=root)
    ).status_code == 400


@pytest.mark.usefixtures("loaded")
async def test_import_runs_and_frameworks(client: AsyncClient, root: dict[str, str]) -> None:
    runs = (await client.get("/api/v1/geography/import-runs", headers=root)).json()
    assert len(runs["items"]) == 1
    run = runs["items"][0]
    assert (run["status"], run["state_code"], run["source_srid"]) == ("succeeded", 1, 32613)
    detail = (await client.get(f"/api/v1/geography/import-runs/{run['id']}", headers=root)).json()
    assert detail["counts"]["tables"]["sections"]["inserted"] == 8
    errors = (
        await client.get(
            f"/api/v1/geography/import-runs/{run['id']}/issues",
            headers=root,
            params={"severity": "error"},
        )
    ).json()
    assert [(i["layer"], i["code"]) for i in errors["items"]] == [("MANZANA", "missing_parent")]
    frameworks = (await client.get("/api/v1/geography/frameworks", headers=root)).json()
    assert frameworks[0]["is_active"] is True


async def test_without_geography_loaded(client: AsyncClient, root: dict[str, str]) -> None:
    response = await client.get("/api/v1/geography/section", headers=root)
    assert response.status_code == 404
    assert response.json()["code"] == "no-active-framework"


# --- scope: the negative cases ---------------------------------------------------------------


@pytest.mark.usefixtures("loaded")
async def test_user_without_scope_sees_nothing(
    client: AsyncClient, make_user: UserFactory, root: dict[str, str]
) -> None:
    _, headers = await _scoped_user(client, make_user, root, [])
    for level in ("state", "municipality", "section", "locality", "neighborhood"):
        page = (await client.get(f"/api/v1/geography/{level}", headers=headers)).json()
        assert page["items"] == [], level
    assert (
        await client.get("/api/v1/geography/search", headers=headers, params={"q": "01-0101"})
    ).json() == []


@pytest.mark.usefixtures("loaded")
async def test_section_scope_limits_every_query(
    client: AsyncClient, make_user: UserFactory, root: dict[str, str], owner_engine: AsyncEngine
) -> None:
    section_101 = await node_id(owner_engine, "sections", "section_number = 101")
    section_104 = await node_id(owner_engine, "sections", "section_number = 104")
    _, headers = await _scoped_user(
        client, make_user, root, [{"level": "section", "node_id": section_101}]
    )

    sections = (await client.get("/api/v1/geography/section", headers=headers)).json()
    assert [s["key"] for s in sections["items"]] == ["01-0101"]
    municipalities = (await client.get("/api/v1/geography/municipality", headers=headers)).json()
    assert [m["key"] for m in municipalities["items"]] == ["01-001"]  # touches 101
    colonias = (await client.get("/api/v1/geography/neighborhood", headers=headers)).json()
    assert [c["key"] for c in colonias["items"]] == ["01-COL-10"]
    localities = (await client.get("/api/v1/geography/locality", headers=headers)).json()
    assert [item["key"] for item in localities["items"]] == ["01-001-0001"]  # via its blocks

    forbidden = await client.get(f"/api/v1/geography/section/{section_104}", headers=headers)
    assert forbidden.status_code == 403
    assert (
        await client.get(f"/api/v1/geography/section/{section_101}", headers=headers)
    ).status_code == 200
    assert (
        await client.get("/api/v1/geography/search", headers=headers, params={"q": "01-0104"})
    ).json() == []

    lon, lat = await lonlat(owner_engine, 3500, 500)  # section 104
    assert (
        await client.get(
            "/api/v1/geography/locate", headers=headers, params={"lat": lat, "lon": lon}
        )
    ).status_code == 403
    lon, lat = await lonlat(owner_engine, 300, 300)  # section 101
    assert (
        await client.get(
            "/api/v1/geography/locate", headers=headers, params={"lat": lat, "lon": lon}
        )
    ).status_code == 200

    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert me["geo_unrestricted"] is False
    assert me["geo_scopes"] == [
        {"id": me["geo_scopes"][0]["id"], "level": "section", "node_id": section_101}
    ]


@pytest.mark.usefixtures("loaded")
async def test_scoped_tiles_only_contain_the_scope(
    client: AsyncClient, make_user: UserFactory, root: dict[str, str], owner_engine: AsyncEngine
) -> None:
    municipality_two = await node_id(owner_engine, "municipalities", "municipality_code = 2")
    _, headers = await _scoped_user(
        client, make_user, root, [{"level": "municipality", "node_id": municipality_two}]
    )
    lon, lat = await lonlat(owner_engine, 2000, 1000)
    n = 2**12
    rad = math.radians(lat)
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.log(math.tan(rad) + 1 / math.cos(rad)) / math.pi) / 2 * n)
    scoped = await client.get(f"/api/v1/geography/tiles/sections/12/{x}/{y}.mvt", headers=headers)
    full = await client.get(f"/api/v1/geography/tiles/sections/12/{x}/{y}.mvt", headers=root)
    assert 0 < len(scoped.content) < len(full.content)
    assert b"101" not in scoped.content
    assert b"104" in scoped.content


@pytest.mark.usefixtures("loaded")
async def test_scope_assignment_cannot_exceed_own_scope(
    client: AsyncClient, make_user: UserFactory, root: dict[str, str], owner_engine: AsyncEngine
) -> None:
    municipality_one = await node_id(owner_engine, "municipalities", "municipality_code = 1")
    state = await node_id(owner_engine, "states", "state_code = 1")
    section_101 = await node_id(owner_engine, "sections", "section_number = 101")
    section_104 = await node_id(owner_engine, "sections", "section_number = 104")
    admin, admin_headers = await _scoped_user(
        client,
        make_user,
        root,
        [{"level": "municipality", "node_id": municipality_one}],
        roles=("admin",),
        with_totp=True,
    )
    target = await make_user(roles=("viewer",))

    within = await client.put(
        f"/api/v1/users/{target.id}/scopes",
        headers=admin_headers,
        json={"scopes": [{"level": "section", "node_id": section_101}]},
    )
    assert within.status_code == 200
    for scope in (
        {"level": "section", "node_id": section_104},
        {"level": "state", "node_id": state},
        {"level": "national"},
    ):
        response = await client.put(
            f"/api/v1/users/{target.id}/scopes", headers=admin_headers, json={"scopes": [scope]}
        )
        assert response.status_code == 403, scope
    # Nor widen their own scope.
    own = await client.put(
        f"/api/v1/users/{admin.id}/scopes",
        headers=admin_headers,
        json={"scopes": [{"level": "state", "node_id": state}]},
    )
    assert own.status_code == 403
    invalid = await client.put(
        f"/api/v1/users/{target.id}/scopes",
        headers=root,
        json={"scopes": [{"level": "section", "node_id": municipality_one}]},
    )
    assert invalid.status_code == 400
    missing_node = await client.put(
        f"/api/v1/users/{target.id}/scopes", headers=root, json={"scopes": [{"level": "state"}]}
    )
    assert missing_node.status_code == 400


@pytest.mark.usefixtures("loaded")
async def test_user_administration_is_limited_by_scope(
    client: AsyncClient, make_user: UserFactory, root: dict[str, str], owner_engine: AsyncEngine
) -> None:
    municipality_one = await node_id(owner_engine, "municipalities", "municipality_code = 1")
    municipality_two = await node_id(owner_engine, "municipalities", "municipality_code = 2")
    section_101 = await node_id(owner_engine, "sections", "section_number = 101")
    _, admin_headers = await _scoped_user(
        client,
        make_user,
        root,
        [{"level": "municipality", "node_id": municipality_one}],
        roles=("admin",),
        with_totp=True,
    )
    inside, _ = await _scoped_user(
        client, make_user, root, [{"level": "section", "node_id": section_101}]
    )
    outside, _ = await _scoped_user(
        client, make_user, root, [{"level": "municipality", "node_id": municipality_two}]
    )
    national, _ = await _scoped_user(client, make_user, root, [{"level": "national"}])
    unassigned = await make_user(roles=("viewer",))

    listed = {
        item["id"]
        for item in (await client.get("/api/v1/users", headers=admin_headers)).json()["items"]
    }
    assert str(inside.id) in listed
    assert str(unassigned.id) in listed  # no scope yet: can be configured
    assert str(outside.id) not in listed
    assert str(national.id) not in listed

    for target in (outside, national):
        assert (
            await client.get(f"/api/v1/users/{target.id}", headers=admin_headers)
        ).status_code == 403
        disabled = await client.post(f"/api/v1/users/{target.id}/disable", headers=admin_headers)
        assert disabled.status_code == 403
        scopes = await client.get(f"/api/v1/users/{target.id}/scopes", headers=admin_headers)
        assert scopes.status_code == 403
    assert (
        await client.post(f"/api/v1/users/{inside.id}/disable", headers=admin_headers)
    ).status_code == 200


@pytest.mark.usefixtures("loaded")
async def test_national_scope_sees_everything(
    client: AsyncClient, make_user: UserFactory, root: dict[str, str]
) -> None:
    _, headers = await _scoped_user(client, make_user, root, [{"level": "national"}])
    sections = (await client.get("/api/v1/geography/section", headers=headers)).json()
    assert len(sections["items"]) == 8
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert me["geo_unrestricted"] is True
