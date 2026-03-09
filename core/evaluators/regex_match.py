# core/evaluators/regex_match.py
import re
from core.models import Score


class RegexEvaluator:
    def __init__(self, pattern: str):
        self.pattern = re.compile(pattern)

    def _run(self, response: str) -> Score:
        if self.pattern.search(response):
            return Score(value=1.0)
        return Score(value=0.0, reason=f"Pattern '{self.pattern.pattern}' not found in response")
