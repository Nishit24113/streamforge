# Schema Registry

Versioned event schemas with backward/forward compatibility enforcement for StreamForge pipelines.

Prevents breaking schema changes from reaching downstream consumers — the same guarantee Confluent Schema Registry provides for Kafka.

---

## Features

- **Schema Versioning** - Every schema change creates an immutable version
- **Compatibility Checks** - Backward, forward, full, and transitive modes
- **Event Validation** - Validate events against registered schemas at ingestion
- **Breaking Change Prevention** - Reject incompatible schema changes before deploy
- **Deduplication** - Identical schemas return existing version

---

## Compatibility Modes

| Mode | Guarantee | Allowed Changes |
|------|-----------|-----------------|
| `none` | No checks | Anything |
| `backward` | New schema reads old data | Add optional fields, add required with default |
| `forward` | Old schema reads new data | Add fields, keep required fields |
| `full` | Both directions | Add optional fields only |
| `backward_transitive` | Backward vs **all** versions | Stricter backward |
| `full_transitive` | Full vs **all** versions | Strictest |

**Default:** `backward` (most common for evolving event producers).

---

## Quick Start

### Register a Schema

```python
from streamforge import SchemaRegistry, CompatibilityMode

registry = SchemaRegistry()

registry.register_schema(
    subject='pipeline-123-events',
    schema={
        'type': 'object',
        'properties': {
            'id': {'type': 'string'},
            'timestamp': {'type': 'string'},
            'amount': {'type': 'number'}
        },
        'required': ['id', 'timestamp']
    },
    compatibility=CompatibilityMode.BACKWARD
)
# -> {'subject': 'pipeline-123-events', 'version': 1, 'schema_id': 'a1b2...', 'status': 'registered'}
```

### Evolve the Schema (compatible change)

```python
# Adding an OPTIONAL field is backward-compatible
registry.register_schema(
    subject='pipeline-123-events',
    schema={
        'type': 'object',
        'properties': {
            'id': {'type': 'string'},
            'timestamp': {'type': 'string'},
            'amount': {'type': 'number'},
            'currency': {'type': 'string'}   # new optional field
        },
        'required': ['id', 'timestamp']
    }
)
# -> version 2 registered
```

### Rejected: Breaking Change

```python
# Adding a REQUIRED field without a default breaks backward compat
registry.register_schema(
    subject='pipeline-123-events',
    schema={
        'properties': {
            'id': {'type': 'string'},
            'user_id': {'type': 'string'}
        },
        'required': ['id', 'user_id']   # user_id is new + required
    }
)
# -> CompatibilityError: Backward compatibility broken against v2:
#    New required field 'user_id' has no default
```

**Fix:** add a default so old data stays readable:

```python
'user_id': {'type': 'string', 'default': 'unknown'}
```

---

## Event Validation

Validate events against the registered schema at ingestion time.

```python
is_valid, errors = registry.validate_event(
    subject='pipeline-123-events',
    event={'id': 'evt-1', 'timestamp': '2026-10-03T10:00:00Z', 'amount': 99.99}
)
# -> (True, [])

is_valid, errors = registry.validate_event(
    subject='pipeline-123-events',
    event={'amount': 'not-a-number'}
)
# -> (False, ["Missing required field: id",
#              "Missing required field: timestamp",
#              "Field 'amount' expected number, got str"])
```

---

## REST API

### Register schema

```bash
curl -X POST https://api.streamforge.com/schemas/pipeline-123-events \
  -H 'Content-Type: application/json' \
  -d '{
    "schema": {"properties": {"id": {"type": "string"}}, "required": ["id"]},
    "compatibility": "backward"
  }'
```

### Get latest schema

```bash
curl https://api.streamforge.com/schemas/pipeline-123-events
```

### List versions

```bash
curl https://api.streamforge.com/schemas/pipeline-123-events/versions
```

### Validate an event

```bash
curl -X POST https://api.streamforge.com/schemas/pipeline-123-events/validate \
  -H 'Content-Type: application/json' \
  -d '{"event": {"id": "evt-1"}}'
# -> {"valid": true, "errors": []}
```

---

## Compatibility Rules Explained

### Backward (new schema reads old data)

Safe when a **consumer upgrades before producers**. Breaks on:
- New required field without a default
- Narrowing a field's type (e.g. `number` → `integer`)

### Forward (old schema reads new data)

Safe when a **producer upgrades before consumers**. Breaks on:
- Removing a required field

### Type Widening

`integer → number` is allowed (an int is always a valid float). All other
type changes are rejected.

---

## Integration with Ingestion

The schema registry plugs into the ingestion path so bad events are
rejected at the edge instead of corrupting downstream state.

```python
# In the ingestion handler
is_valid, errors = registry.validate_event(subject, event)

if not is_valid:
    # Route to dead-letter queue with validation errors
    send_to_dlq(event, reason='schema_validation', errors=errors)
    return

# Event is valid — continue processing
process_event(event)
```

---

## CDK Deployment

```typescript
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';

// Schema metadata table (subject + version composite key)
const schemaTable = new dynamodb.Table(this, 'Schemas', {
  partitionKey: { name: 'subject', type: dynamodb.AttributeType.STRING },
  sortKey: { name: 'version', type: dynamodb.AttributeType.NUMBER },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST
});

// Immutable schema store
const schemaBucket = new s3.Bucket(this, 'SchemaStore', {
  versioned: true
});

// Registry Lambda
const registry = new lambda.Function(this, 'SchemaRegistry', {
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'registry.lambda_handler',
  code: lambda.Code.fromAsset('services/schema')
});

schemaTable.grantReadWriteData(registry);
schemaBucket.grantReadWrite(registry);
```

---

## Testing

```bash
pytest tests/test_schema_registry.py -v
```

Covers backward/forward checks, type widening, event validation, and
compatibility-mode enforcement.

---

## Roadmap

- **Avro / Protobuf support** - Beyond JSON Schema
- **Schema references** - Compose schemas from shared sub-schemas
- **Consumer tracking** - Know which consumers use which version
- **Auto-migration hints** - Suggest safe migration paths for breaking changes

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
