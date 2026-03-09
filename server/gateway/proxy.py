# server/gateway/proxy.py — async HTTP proxy forwarder
from __future__ import annotations
from dataclasses import dataclass
import httpx


class ProxyError(Exception):
    pass


@dataclass
class ProxyResponse:
    status_code: int
    text: str
    headers: dict


async def forward_request(
    target: str,
    body: dict,
    headers: dict,
    timeout: float = 30.0,
) -> ProxyResponse:
    """Forward a POST request to the target agent and return its raw response."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                target,
                json=body,
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            return ProxyResponse(
                status_code=resp.status_code,
                text=resp.text,
                headers=dict(resp.headers),
            )
    except httpx.HTTPStatusError as exc:
        raise ProxyError(
            f"Target returned {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except httpx.TransportError as exc:
        raise ProxyError(str(exc)) from exc
