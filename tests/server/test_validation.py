# tests/server/test_validation.py
import pytest
from server.gateway.validation import validate_request_body, RequestValidationError


def test_valid_body_passes():
    schema = {
        "type": "object",
        "required": ["message"],
        "properties": {"message": {"type": "string"}},
    }
    # Should not raise
    validate_request_body({"message": "hello"}, schema)


def test_missing_required_field_raises():
    schema = {
        "type": "object",
        "required": ["message"],
        "properties": {"message": {"type": "string"}},
    }
    with pytest.raises(RequestValidationError) as exc_info:
        validate_request_body({}, schema)
    assert "message" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()


def test_wrong_type_raises():
    schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
    with pytest.raises(RequestValidationError):
        validate_request_body({"count": "not-an-int"}, schema)


def test_empty_schema_allows_anything():
    # An empty schema {} validates everything
    validate_request_body({"anything": "goes"}, {})


def test_violations_list_has_detail():
    schema = {
        "type": "object",
        "required": ["order_id", "amount"],
        "properties": {
            "order_id": {"type": "string"},
            "amount": {"type": "number"},
        },
    }
    with pytest.raises(RequestValidationError) as exc_info:
        validate_request_body({}, schema)
    err = exc_info.value
    assert len(err.violations) > 0
    assert all("field" in v or "message" in v for v in err.violations)
