# core/evaluators/contains.py
from core.models import Score


class ContainsEvaluator:
    def __init__(self, substring: str, case_sensitive: bool = True):
        self.substring = substring
        self.case_sensitive = case_sensitive

    def _run(self, response: str) -> Score:
        haystack = response if self.case_sensitive else response.lower()
        needle = self.substring if self.case_sensitive else self.substring.lower()
        if needle in haystack:
            return Score(value=1.0)
        return Score(value=0.0, reason=f"Response does not contain '{self.substring}'")
