import asyncio
from math import isfinite

import httpx

TURN_TRAFFIC = '8 / 1e6 * sum(rate({__name__=~"turn_total_traffic_(rcvb|sentb)(_total)?"}[5m]))'
JOIN_ATTEMPTS = "sum(increase(join_room_duration_seconds_count[24h]))"
JOIN_SUCCESS = f"100 * sum(increase(room_joins_total[24h])) / ({JOIN_ATTEMPTS} > 0)"


async def query(client: httpx.AsyncClient, url: str, expression: str) -> float | None:
    try:
        response = await client.get(url, params={"query": expression})
        response.raise_for_status()
        value = float(response.json()["data"]["result"][0]["value"][1])
        return value if isfinite(value) and value >= 0 else None
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, IndexError, TypeError):
        return None


async def dashboard_telemetry(base_url: str) -> tuple[float | None, float | None]:
    if not base_url:
        return None, None
    endpoint = base_url.rstrip("/") + "/api/v1/query"
    async with httpx.AsyncClient(timeout=1.0, trust_env=False) as client:
        turn, joins = await asyncio.gather(
            query(client, endpoint, TURN_TRAFFIC), query(client, endpoint, JOIN_SUCCESS)
        )
    return turn, min(joins, 100) if joins is not None else None
