# tests/server/test_proxy.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from server.gateway.proxy import forward_request, ProxyError


@pytest.mark.asyncio
async def test_forward_returns_response_text():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"answer": "42"}'
    mock_response.headers = {"content-type": "application/json"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("server.gateway.proxy.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await forward_request(
            target="http://agent:8000/chat",
            body={"input": "hello"},
            headers={},
        )

    assert result.status_code == 200
    assert result.text == '{"answer": "42"}'


@pytest.mark.asyncio
async def test_forward_raises_proxy_error_on_connection_failure():
    import httpx

    with patch("server.gateway.proxy.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(ProxyError, match="refused"):
            await forward_request(
                target="http://dead-agent:9999/chat",
                body={"input": "hello"},
                headers={},
            )


@pytest.mark.asyncio
async def test_forward_passes_custom_headers():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "{}"
    mock_response.headers = {}
    mock_response.raise_for_status = MagicMock()

    captured_headers: dict = {}

    async def capture_post(url, json, headers, timeout):
        captured_headers.update(headers)
        return mock_response

    mock_client = AsyncMock()
    mock_client.post = capture_post

    with patch("server.gateway.proxy.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        await forward_request(
            target="http://agent/chat",
            body={},
            headers={"X-Trace-Id": "abc123"},
        )

    assert captured_headers.get("X-Trace-Id") == "abc123"
