# core/evaluators/json_schema_valid.py
import json
import jsonschema
from core.models import Score


class JsonSchemaEvaluator:
    def __init__(self, schema: dict):
        self.schema = schema

    def _run(self, response: str) -> Score:
        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            return Score(value=0.0, reason=f"Invalid JSON: {e}")
        try:
            jsonschema.validate(data, self.schema)
            return Score(value=1.0)
        except jsonschema.ValidationError as e:
            return Score(value=0.0, reason=e.message)
