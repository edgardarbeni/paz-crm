"""Geography benchmark against a running API (D-19 / CLAUDE.md: p95 < 50 ms locate, < 200 ms reads).

Usage (stack up, national data imported):
    cd backend && uv run python ../scripts/benchmark_geo.py --email bench@example.com --password ...

The user must be a superadmin; on first run the script enrolls TOTP and prints the secret so it
can be reused with --totp-secret.
"""

import argparse
import statistics
import time

import httpx
import pyotp

BASE = "https://localhost"


def p(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def login(client: httpx.Client, email: str, password: str, secret: str | None) -> tuple[str, str | None]:
    body = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()
    if body["status"] == "mfa_required":
        assert secret, "La cuenta tiene TOTP: pasa --totp-secret"
        body = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": body["mfa_token"], "code": pyotp.TOTP(secret).now()}).json()
    token = body["access_token"]
    if body["scope"] == "mfa_enrollment":
        headers = {"Authorization": f"Bearer {token}"}
        secret = client.post("/api/v1/auth/mfa/totp/setup", headers=headers).json()["secret"]
        token = client.post("/api/v1/auth/mfa/totp/confirm", headers=headers, json={"code": pyotp.TOTP(secret).now()}).json()["access_token"]
        print(f"TOTP enrolado; secreto para próximas corridas: {secret}")
    return token, secret


def timed(client: httpx.Client, headers: dict[str, str], url: str, params: dict[str, object] | None = None) -> float:
    start = time.perf_counter()
    response = client.get(url, headers=headers, params=params)
    elapsed = (time.perf_counter() - start) * 1000
    assert response.status_code in (200, 404), (url, response.status_code, response.text[:200])
    return elapsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--totp-secret")
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--points", required=True, help="Archivo con 'lon,lat' por línea")
    args = parser.parse_args()

    client = httpx.Client(base_url=BASE, verify=False, timeout=30)
    token, _ = login(client, args.email, args.password, args.totp_secret)
    headers = {"Authorization": f"Bearer {token}"}
    points = [tuple(map(float, line.split(","))) for line in open(args.points, encoding="utf-8") if line.strip()]

    results: dict[str, list[float]] = {}
    for lon, lat in points[: args.samples]:
        results.setdefault("locate", []).append(timed(client, headers, "/api/v1/geography/locate", {"lat": lat, "lon": lon}))
    for _ in range(min(args.samples, 200)):
        results.setdefault("list sections (50)", []).append(timed(client, headers, "/api/v1/geography/section", {"limit": 50}))
        results.setdefault("search key", []).append(timed(client, headers, "/api/v1/geography/search", {"q": "15-1234"}))
        results.setdefault("search name", []).append(timed(client, headers, "/api/v1/geography/search", {"q": "guadalupe"}))
    print(f"{'endpoint':<22}{'n':>6}{'p50 ms':>10}{'p95 ms':>10}{'max ms':>10}")
    for name, values in results.items():
        print(f"{name:<22}{len(values):>6}{statistics.median(values):>10.1f}{p(values, 0.95):>10.1f}{max(values):>10.1f}")


if __name__ == "__main__":
    main()
