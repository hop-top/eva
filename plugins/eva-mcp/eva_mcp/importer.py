from __future__ import annotations
from pathlib import Path
import yaml
from core.models import Contract, RetryPolicy


class MCPImportError(Exception):
    pass


def import_mcp_manifest(manifest: dict) -> list[Contract]:
    """
    Convert an MCP server manifest JSON dict into a list of Eva contracts.
    One contract is produced per tool in manifest['tools'].
    """
    name = manifest.get("name")
    if not name:
        raise MCPImportError("MCP manifest must have a 'name' field")

    contracts = []
    for tool in manifest.get("tools", []):
        tool_name = tool.get("name", "unknown")
        request_schema = tool.get("inputSchema", {})
        contracts.append(
            Contract(
                name=f"{name}.{tool_name}",
                provider=name,
                consumer=None,
                request_schema=request_schema,
                evaluators=[],
                retry_policy=RetryPolicy(),
            )
        )
    return contracts


def contracts_to_yaml(contracts: list[Contract], output_dir: Path) -> list[Path]:
    """Write each contract as a YAML file. Returns list of written paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for contract in contracts:
        filename = contract.name.replace("/", "_").replace(".", "_") + ".yaml"
        path = output_dir / filename
        data = {
            "name": contract.name,
            "provider": contract.provider,
            "request_schema": contract.request_schema,
            "evaluators": [e.model_dump() for e in contract.evaluators],
            "retry_policy": contract.retry_policy.model_dump(),
        }
        if contract.consumer:
            data["consumer"] = contract.consumer
        path.write_text(yaml.dump(data, sort_keys=False))
        paths.append(path)
    return paths
