# core/contract.py
from pathlib import Path
import yaml
from pydantic import ValidationError
from core.models import Contract


class ContractValidationError(Exception):
    pass


def load_contract(path: Path) -> Contract:
    if not path.exists():
        raise FileNotFoundError(f"Contract file not found: {path}")
    raw = yaml.safe_load(path.read_text())
    if not raw or "name" not in raw:
        raise ContractValidationError("Contract must have a 'name' field")
    try:
        return Contract.model_validate(raw)
    except ValidationError as e:
        raise ContractValidationError(str(e)) from e
