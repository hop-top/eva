# server/gateway/validation.py — request body JSON Schema validation
from __future__ import annotations
import jsonschema


class RequestValidationError(Exception):
    def __init__(self, message: str, violations: list[dict]) -> None:
        super().__init__(message)
        self.violations = violations


def validate_request_body(body: dict, schema: dict) -> None:
    """Validate body against JSON Schema. Raises RequestValidationError on failure."""
    if not schema:
        return
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(body), key=lambda e: list(e.path))
    if not errors:
        return
    violations = [
        {
            "field": ".".join(str(p) for p in err.absolute_path) or "$root",
            "message": err.message,
        }
        for err in errors
    ]
    raise RequestValidationError(
        f"Request body failed schema validation: {violations[0]['message']}",
        violations=violations,
    )
