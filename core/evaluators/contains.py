# core/evaluators/contains.py
from core.evaluators._field import extract_text_field
from core.models import Score


class ContainsEvaluator:
    def __init__(self, substring: str, case_sensitive: bool = True, field: str | None = None):
        self.substring = substring
        self.case_sensitive = case_sensitive
        self.field = field

    def run(self, response: str) -> Score:
        if self.field:
            response, err = extract_text_field(response, self.field, "contains")
            if err is not None:
                return err
        haystack = response if self.case_sensitive else response.lower()
        needle = self.substring if self.case_sensitive else self.substring.lower()
        if needle in haystack:
            return Score(value=1.0)
        return Score(value=0.0, reason=f"Response does not contain '{self.substring}'")

    _run = run  # deprecated alias; remove in v0.2.0
