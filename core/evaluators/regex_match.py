# core/evaluators/regex_match.py
import re
from core.evaluators._field import extract_text_field
from core.models import Score


class RegexEvaluator:
    def __init__(self, pattern: str, field: str | None = None):
        self.pattern = re.compile(pattern)
        self.field = field

    def run(self, response: str) -> Score:
        if self.field:
            response, err = extract_text_field(response, self.field, "regex")
            if err is not None:
                return err
        if self.pattern.search(response):
            return Score(value=1.0)
        return Score(value=0.0, reason=f"Pattern '{self.pattern.pattern}' not found in response")

    _run = run  # deprecated alias; remove in v0.2.0
