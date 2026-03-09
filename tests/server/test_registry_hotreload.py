# tests/server/test_registry_hotreload.py — hot-reload watcher tests
import asyncio
import pytest
import yaml
from pathlib import Path
from server.contracts.registry import ContractRegistry


@pytest.mark.asyncio
async def test_watch_dir_reloads_on_change(tmp_path):
    """Registry picks up a new file written after watch starts."""
    contract_data = {
        "name": "hot_contract",
        "provider": "agent-hot",
        "request_schema": {"type": "object"},
        "evaluators": [],
        "retry_policy": {"max_retries": 1},
    }

    registry = ContractRegistry()

    # Start watcher as a background task
    watch_task = asyncio.create_task(registry.watch_dir(tmp_path))

    # Give the watcher time to start
    await asyncio.sleep(0.1)

    # Write a new contract file
    f = tmp_path / "hot_contract.yaml"
    f.write_text(yaml.dump(contract_data))

    # Poll for up to 3s for the registry to pick it up
    for _ in range(30):
        await asyncio.sleep(0.1)
        if registry.get("hot_contract") is not None:
            break

    watch_task.cancel()
    try:
        await watch_task
    except asyncio.CancelledError:
        pass

    assert registry.get("hot_contract") is not None
    assert registry.get("hot_contract").provider == "agent-hot"
