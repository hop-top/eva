# server/contracts/registry.py — in-memory contract registry with hot-reload support
from __future__ import annotations
import warnings
from pathlib import Path
from core.contract import load_contract
from core.models import Contract


class ContractRegistry:
    """In-memory contract registry. Thread-safe for reads; reload is not concurrent."""

    def __init__(self) -> None:
        self._contracts: dict[str, Contract] = {}

    def load_file(self, path: Path) -> None:
        contract = load_contract(path)
        self._contracts[contract.name] = contract

    def load_dir(self, directory: Path) -> None:
        for yaml_file in sorted(directory.glob("*.yaml")):
            try:
                self.load_file(yaml_file)
            except Exception as exc:
                warnings.warn(f"Skipping {yaml_file}: {exc}")

    def get(self, name: str) -> Contract | None:
        return self._contracts.get(name)

    def all(self) -> list[Contract]:
        return list(self._contracts.values())

    def list_names(self) -> list[str]:
        return list(self._contracts.keys())

    async def watch_dir(self, directory: Path) -> None:
        """Watch a directory for YAML changes and hot-reload. Runs until cancelled."""
        from watchfiles import awatch
        async for changes in awatch(str(directory)):
            for _change_type, path_str in changes:
                path = Path(path_str)
                if path.suffix in (".yaml", ".yml"):
                    try:
                        self.load_file(path)
                    except Exception as exc:
                        warnings.warn(f"Hot-reload failed for {path}: {exc}")
