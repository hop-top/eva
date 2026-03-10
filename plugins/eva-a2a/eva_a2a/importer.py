from __future__ import annotations
from pathlib import Path
import yaml
from core.models import Contract, RetryPolicy


class A2AImportError(Exception):
    pass


def import_agent_card(card: dict) -> list[Contract]:
    """
    Convert an A2A Agent Card JSON dict into a list of Eva contracts.
    One contract is produced per skill in card['skills'].
    """
    name = card.get("name")
    if not name:
        raise A2AImportError("Agent Card must have a 'name' field")

    contracts = []
    for skill in card.get("skills", []):
        skill_name = skill.get("name", "unknown")
        request_schema = skill.get("inputSchema", {})
        contracts.append(
            Contract(
                name=f"{name}.{skill_name}",
                provider=name,
                consumer=None,
                request_schema=request_schema,
                evaluators=[],
                retry_policy=RetryPolicy(),
            )
        )
    return contracts


def contracts_to_yaml(contracts: list[Contract], output_dir: Path) -> list[Path]:
    """Write each contract as a YAML file in output_dir. Returns list of written paths."""
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
