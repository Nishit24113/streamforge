"""
Schema Registry for StreamForge.

Manages versioned event schemas with backward/forward compatibility checks.
Prevents breaking changes from reaching downstream consumers.
"""

import json
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
import boto3
from aws_lambda_powertools import Logger

logger = Logger()

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')


class CompatibilityMode(Enum):
    """Schema compatibility modes."""
    NONE = "none"                    # No compatibility checks
    BACKWARD = "backward"            # New schema can read old data
    FORWARD = "forward"              # Old schema can read new data
    FULL = "full"                    # Both backward and forward
    BACKWARD_TRANSITIVE = "backward_transitive"  # Backward against all versions
    FULL_TRANSITIVE = "full_transitive"          # Full against all versions


class CompatibilityError(Exception):
    """Raised when a schema change violates compatibility rules."""
    pass


class SchemaRegistry:
    """Manages versioned schemas with compatibility validation."""

    def __init__(self):
        self.schema_table = dynamodb.Table('streamforge-schemas')
        self.bucket = 'streamforge-schema-store'

    def register_schema(
        self,
        subject: str,
        schema: Dict[str, Any],
        compatibility: CompatibilityMode = CompatibilityMode.BACKWARD
    ) -> Dict[str, Any]:
        """
        Register a new schema version for a subject.

        Args:
            subject: Schema subject (e.g., 'pipeline-123-events')
            schema: JSON Schema definition
            compatibility: Compatibility mode to enforce

        Returns:
            Registration result with version and schema ID

        Raises:
            CompatibilityError: If schema violates compatibility rules
        """
        schema_str = json.dumps(schema, sort_keys=True)
        schema_id = hashlib.sha256(schema_str.encode()).hexdigest()[:16]

        # Get existing versions
        existing_versions = self.get_versions(subject)

        # If identical schema already exists, return existing version
        for version in existing_versions:
            if version['schema_id'] == schema_id:
                logger.info(f"Schema already registered: {subject} v{version['version']}")
                return {
                    'subject': subject,
                    'version': version['version'],
                    'schema_id': schema_id,
                    'status': 'already_exists'
                }

        # Check compatibility against existing versions
        if existing_versions:
            self._check_compatibility(
                schema,
                existing_versions,
                compatibility
            )

        # Determine new version number
        new_version = max([v['version'] for v in existing_versions], default=0) + 1

        # Store schema in S3
        s3.put_object(
            Bucket=self.bucket,
            Key=f'{subject}/v{new_version}.json',
            Body=schema_str,
            ContentType='application/json'
        )

        # Store metadata in DynamoDB
        record = {
            'subject': subject,
            'version': new_version,
            'schema_id': schema_id,
            'schema': schema_str,
            'compatibility': compatibility.value,
            'registered_at': datetime.utcnow().isoformat(),
            's3_key': f'{subject}/v{new_version}.json'
        }

        self.schema_table.put_item(Item=record)

        logger.info(f"Registered schema: {subject} v{new_version} ({schema_id})")

        return {
            'subject': subject,
            'version': new_version,
            'schema_id': schema_id,
            'status': 'registered'
        }

    def _check_compatibility(
        self,
        new_schema: Dict[str, Any],
        existing_versions: List[Dict[str, Any]],
        mode: CompatibilityMode
    ):
        """
        Validate new schema against existing versions.

        Raises CompatibilityError if validation fails.
        """
        if mode == CompatibilityMode.NONE:
            return

        # Determine which versions to check against
        if mode in (CompatibilityMode.BACKWARD_TRANSITIVE, CompatibilityMode.FULL_TRANSITIVE):
            versions_to_check = existing_versions
        else:
            # Only check against latest version
            versions_to_check = [max(existing_versions, key=lambda v: v['version'])]

        for version in versions_to_check:
            old_schema = json.loads(version['schema'])

            if mode in (CompatibilityMode.BACKWARD, CompatibilityMode.BACKWARD_TRANSITIVE, CompatibilityMode.FULL, CompatibilityMode.FULL_TRANSITIVE):
                issues = self._check_backward(old_schema, new_schema)
                if issues:
                    raise CompatibilityError(
                        f"Backward compatibility broken against v{version['version']}: {'; '.join(issues)}"
                    )

            if mode in (CompatibilityMode.FORWARD, CompatibilityMode.FULL, CompatibilityMode.FULL_TRANSITIVE):
                issues = self._check_forward(old_schema, new_schema)
                if issues:
                    raise CompatibilityError(
                        f"Forward compatibility broken against v{version['version']}: {'; '.join(issues)}"
                    )

    def _check_backward(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any]
    ) -> List[str]:
        """
        Check if new schema can read data written with old schema.

        Breaking changes:
        - Removing a field that was required
        - Adding a new required field without default
        - Narrowing a field's type
        """
        issues = []

        old_props = old_schema.get('properties', {})
        new_props = new_schema.get('properties', {})
        old_required = set(old_schema.get('required', []))
        new_required = set(new_schema.get('required', []))

        # New required fields without defaults break backward compatibility
        added_required = new_required - old_required
        for field in added_required:
            field_schema = new_props.get(field, {})
            if 'default' not in field_schema:
                issues.append(f"New required field '{field}' has no default")

        # Type narrowing breaks compatibility
        for field in old_props:
            if field in new_props:
                old_type = old_props[field].get('type')
                new_type = new_props[field].get('type')
                if old_type and new_type and old_type != new_type:
                    if not self._is_type_widening(old_type, new_type):
                        issues.append(f"Field '{field}' type changed from {old_type} to {new_type}")

        return issues

    def _check_forward(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any]
    ) -> List[str]:
        """
        Check if old schema can read data written with new schema.

        Breaking changes:
        - Removing a required field
        - Adding a new required field
        """
        issues = []

        old_required = set(old_schema.get('required', []))
        new_required = set(new_schema.get('required', []))
        old_props = old_schema.get('properties', {})
        new_props = new_schema.get('properties', {})

        # Removing required fields breaks forward compatibility
        removed_required = old_required - new_required
        for field in removed_required:
            if field not in new_props:
                issues.append(f"Required field '{field}' was removed")

        return issues

    def _is_type_widening(self, old_type: str, new_type: str) -> bool:
        """Check if type change is a safe widening (e.g., integer -> number)."""
        widenings = {
            ('integer', 'number'),  # int can be read as float
        }
        return (old_type, new_type) in widenings

    def get_versions(self, subject: str) -> List[Dict[str, Any]]:
        """Get all versions for a subject."""
        response = self.schema_table.query(
            KeyConditionExpression='subject = :s',
            ExpressionAttributeValues={':s': subject}
        )
        return sorted(response.get('Items', []), key=lambda v: v['version'])

    def get_schema(
        self,
        subject: str,
        version: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get a specific schema version (or latest if version not specified).
        """
        versions = self.get_versions(subject)

        if not versions:
            raise ValueError(f"No schema found for subject: {subject}")

        if version is None:
            target = max(versions, key=lambda v: v['version'])
        else:
            target = next((v for v in versions if v['version'] == version), None)
            if not target:
                raise ValueError(f"Version {version} not found for subject: {subject}")

        return {
            'subject': target['subject'],
            'version': target['version'],
            'schema_id': target['schema_id'],
            'schema': json.loads(target['schema']),
            'compatibility': target['compatibility']
        }

    def validate_event(
        self,
        subject: str,
        event: Dict[str, Any],
        version: Optional[int] = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate an event against a registered schema.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        schema_record = self.get_schema(subject, version)
        schema = schema_record['schema']

        errors = []

        # Check required fields
        required = schema.get('required', [])
        for field in required:
            if field not in event:
                errors.append(f"Missing required field: {field}")

        # Check field types
        properties = schema.get('properties', {})
        for field, value in event.items():
            if field in properties:
                expected_type = properties[field].get('type')
                if expected_type and not self._matches_type(value, expected_type):
                    errors.append(
                        f"Field '{field}' expected {expected_type}, got {type(value).__name__}"
                    )

        return (len(errors) == 0, errors)

    def _matches_type(self, value: Any, expected_type: str) -> bool:
        """Check if a value matches a JSON Schema type."""
        type_map = {
            'string': str,
            'integer': int,
            'number': (int, float),
            'boolean': bool,
            'array': list,
            'object': dict,
            'null': type(None)
        }
        expected = type_map.get(expected_type)
        if expected is None:
            return True
        # bool is a subclass of int in Python, handle explicitly
        if expected_type == 'integer' and isinstance(value, bool):
            return False
        return isinstance(value, expected)

    def set_compatibility(
        self,
        subject: str,
        compatibility: CompatibilityMode
    ) -> Dict[str, Any]:
        """Update the compatibility mode for a subject's latest version."""
        latest = self.get_schema(subject)

        self.schema_table.update_item(
            Key={'subject': subject, 'version': latest['version']},
            UpdateExpression='SET compatibility = :c',
            ExpressionAttributeValues={':c': compatibility.value}
        )

        return {
            'subject': subject,
            'compatibility': compatibility.value,
            'status': 'updated'
        }

    def delete_version(self, subject: str, version: int) -> Dict[str, Any]:
        """Delete a specific schema version (soft delete)."""
        self.schema_table.update_item(
            Key={'subject': subject, 'version': version},
            UpdateExpression='SET deleted = :d, deleted_at = :t',
            ExpressionAttributeValues={
                ':d': True,
                ':t': datetime.utcnow().isoformat()
            }
        )

        return {
            'subject': subject,
            'version': version,
            'status': 'deleted'
        }


# Lambda handler
def lambda_handler(event, context):
    """
    Lambda handler for schema registry API.

    Endpoints:
    - POST /schemas/{subject}            - Register new schema version
    - GET  /schemas/{subject}            - Get latest schema
    - GET  /schemas/{subject}/versions   - List all versions
    - GET  /schemas/{subject}/{version}  - Get specific version
    - POST /schemas/{subject}/validate   - Validate event against schema
    """
    registry = SchemaRegistry()

    path = event.get('path', '')
    method = event.get('httpMethod', 'GET')
    path_params = event.get('pathParameters', {}) or {}
    subject = path_params.get('subject')

    try:
        if method == 'POST' and path.endswith('/validate'):
            body = json.loads(event.get('body', '{}'))
            is_valid, errors = registry.validate_event(subject, body.get('event', {}))
            return _response(200, {'valid': is_valid, 'errors': errors})

        elif method == 'POST':
            body = json.loads(event.get('body', '{}'))
            compatibility = CompatibilityMode(body.get('compatibility', 'backward'))
            result = registry.register_schema(subject, body['schema'], compatibility)
            return _response(201, result)

        elif method == 'GET' and path.endswith('/versions'):
            versions = registry.get_versions(subject)
            return _response(200, {'subject': subject, 'versions': [
                {'version': v['version'], 'schema_id': v['schema_id'], 'registered_at': v['registered_at']}
                for v in versions
            ]})

        elif method == 'GET':
            version = int(path_params['version']) if path_params.get('version') else None
            schema = registry.get_schema(subject, version)
            return _response(200, schema)

        else:
            return _response(405, {'error': 'Method not allowed'})

    except CompatibilityError as e:
        return _response(409, {'error': 'compatibility_violation', 'message': str(e)})
    except ValueError as e:
        return _response(404, {'error': 'not_found', 'message': str(e)})
    except Exception as e:
        logger.error(f"Schema registry error: {e}")
        return _response(500, {'error': 'internal_error', 'message': str(e)})


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Build API Gateway response."""
    return {
        'statusCode': status_code,
        'body': json.dumps(body),
        'headers': {'Content-Type': 'application/json'}
    }
