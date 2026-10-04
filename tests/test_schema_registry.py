"""
Tests for the Schema Registry compatibility logic.

Focuses on the pure compatibility-checking functions, which contain
the core business logic and require no AWS mocking.
"""

import sys
import pytest
from unittest.mock import MagicMock, patch

# Stub aws_lambda_powertools so the module imports without the Lambda runtime dep
if 'aws_lambda_powertools' not in sys.modules:
    powertools_stub = MagicMock()
    powertools_stub.Logger = MagicMock(return_value=MagicMock())
    sys.modules['aws_lambda_powertools'] = powertools_stub

with patch('boto3.resource'), patch('boto3.client'):
    from services.schema.registry import (
        SchemaRegistry,
        CompatibilityMode,
        CompatibilityError,
    )


@pytest.fixture
def registry():
    with patch('boto3.resource'), patch('boto3.client'):
        return SchemaRegistry()


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

def test_backward_adding_optional_field_is_compatible(registry):
    old = {'properties': {'id': {'type': 'string'}}, 'required': ['id']}
    new = {
        'properties': {'id': {'type': 'string'}, 'name': {'type': 'string'}},
        'required': ['id'],
    }
    assert registry._check_backward(old, new) == []


def test_backward_new_required_field_without_default_breaks(registry):
    old = {'properties': {'id': {'type': 'string'}}, 'required': ['id']}
    new = {
        'properties': {'id': {'type': 'string'}, 'email': {'type': 'string'}},
        'required': ['id', 'email'],
    }
    issues = registry._check_backward(old, new)
    assert len(issues) == 1
    assert 'email' in issues[0]


def test_backward_new_required_field_with_default_is_compatible(registry):
    old = {'properties': {'id': {'type': 'string'}}, 'required': ['id']}
    new = {
        'properties': {
            'id': {'type': 'string'},
            'status': {'type': 'string', 'default': 'active'},
        },
        'required': ['id', 'status'],
    }
    assert registry._check_backward(old, new) == []


def test_backward_type_change_breaks(registry):
    old = {'properties': {'amount': {'type': 'string'}}}
    new = {'properties': {'amount': {'type': 'boolean'}}}
    issues = registry._check_backward(old, new)
    assert len(issues) == 1
    assert 'amount' in issues[0]


def test_backward_integer_to_number_is_safe_widening(registry):
    old = {'properties': {'amount': {'type': 'integer'}}}
    new = {'properties': {'amount': {'type': 'number'}}}
    assert registry._check_backward(old, new) == []


# ---------------------------------------------------------------------------
# Forward compatibility
# ---------------------------------------------------------------------------

def test_forward_removing_required_field_breaks(registry):
    old = {
        'properties': {'id': {'type': 'string'}, 'name': {'type': 'string'}},
        'required': ['id', 'name'],
    }
    new = {'properties': {'id': {'type': 'string'}}, 'required': ['id']}
    issues = registry._check_forward(old, new)
    assert len(issues) == 1
    assert 'name' in issues[0]


def test_forward_keeping_field_optional_is_compatible(registry):
    old = {
        'properties': {'id': {'type': 'string'}, 'name': {'type': 'string'}},
        'required': ['id', 'name'],
    }
    new = {
        'properties': {'id': {'type': 'string'}, 'name': {'type': 'string'}},
        'required': ['id'],
    }
    assert registry._check_forward(old, new) == []


# ---------------------------------------------------------------------------
# Event validation
# ---------------------------------------------------------------------------

def test_matches_type_bool_is_not_integer(registry):
    assert registry._matches_type(True, 'integer') is False


def test_matches_type_integer_is_number(registry):
    assert registry._matches_type(5, 'number') is True


def test_matches_type_string(registry):
    assert registry._matches_type('hello', 'string') is True
    assert registry._matches_type(5, 'string') is False


def test_validate_event_missing_required_field(registry):
    schema = {
        'subject': 'test',
        'version': 1,
        'schema_id': 'abc',
        'schema': {
            'properties': {'id': {'type': 'string'}},
            'required': ['id'],
        },
        'compatibility': 'backward',
    }
    registry.get_schema = MagicMock(return_value=schema)

    is_valid, errors = registry.validate_event('test', {})
    assert is_valid is False
    assert any('id' in e for e in errors)


def test_validate_event_wrong_type(registry):
    schema = {
        'subject': 'test',
        'version': 1,
        'schema_id': 'abc',
        'schema': {
            'properties': {'amount': {'type': 'number'}},
            'required': [],
        },
        'compatibility': 'backward',
    }
    registry.get_schema = MagicMock(return_value=schema)

    is_valid, errors = registry.validate_event('test', {'amount': 'not-a-number'})
    assert is_valid is False
    assert any('amount' in e for e in errors)


def test_validate_event_valid(registry):
    schema = {
        'subject': 'test',
        'version': 1,
        'schema_id': 'abc',
        'schema': {
            'properties': {
                'id': {'type': 'string'},
                'amount': {'type': 'number'},
            },
            'required': ['id'],
        },
        'compatibility': 'backward',
    }
    registry.get_schema = MagicMock(return_value=schema)

    is_valid, errors = registry.validate_event('test', {'id': 'evt-1', 'amount': 99.99})
    assert is_valid is True
    assert errors == []


# ---------------------------------------------------------------------------
# Compatibility mode enforcement
# ---------------------------------------------------------------------------

def test_check_compatibility_none_mode_skips(registry):
    old_versions = [{'version': 1, 'schema': '{"properties": {"id": {"type": "string"}}, "required": ["id"]}'}]
    new = {'properties': {}, 'required': ['new_field']}
    # Should not raise even though this would break backward compat
    registry._check_compatibility(new, old_versions, CompatibilityMode.NONE)


def test_check_compatibility_backward_raises_on_break(registry):
    old_versions = [{
        'version': 1,
        'schema': '{"properties": {"id": {"type": "string"}}, "required": ["id"]}',
    }]
    new = {
        'properties': {'id': {'type': 'string'}, 'email': {'type': 'string'}},
        'required': ['id', 'email'],
    }
    with pytest.raises(CompatibilityError):
        registry._check_compatibility(new, old_versions, CompatibilityMode.BACKWARD)
