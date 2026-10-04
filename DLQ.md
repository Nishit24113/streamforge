# Dead-Letter Queue (DLQ) Replay

Inspect and replay events that failed processing, instead of silently dropping them.

When an event fails — schema validation, a transform exception, a downstream
timeout, or throttling — it lands in the pipeline's DLQ with a failure reason
attached. Once the root cause is fixed, operators replay the affected events
back into the pipeline.

---

## Why This Matters

Without a DLQ, a single bad schema change or a downstream outage means lost data.
With replay, failures are **recoverable**:

1. Events fail → routed to DLQ with reason + error details
2. Operator inspects failures grouped by reason
3. Root cause fixed (e.g. schema updated, downstream back online)
4. Operator replays → events re-enter the pipeline

---

## Failure Reasons

| Reason | Cause | Typical Fix |
|--------|-------|-------------|
| `schema_validation` | Event failed [schema registry](SCHEMA.md) checks | Update schema or fix producer |
| `transform_error` | A transform step threw | Fix transform logic, redeploy |
| `downstream_timeout` | Sink (S3, external API) timed out | Wait for recovery, then replay |
| `throttled` | Kinesis / downstream throttling | Replay at a slower rate |
| `unknown` | Unclassified / malformed message | Inspect manually |

---

## Inspect

Peek at DLQ contents **without removing messages** (uses a short SQS visibility
timeout so messages return to the queue).

```python
from streamforge.dlq import DLQReplayService, FailureReason

service = DLQReplayService(
    dlq_url='https://sqs.us-west-2.amazonaws.com/000/pipeline-123-dlq',
    stream_name='pipeline-123-stream'
)

summary = service.inspect(max_messages=100)
# {
#   'total_inspected': 42,
#   'by_reason': {'schema_validation': 38, 'transform_error': 4},
#   'samples': [{'message_id': ..., 'failure_reason': 'schema_validation',
#                'errors': ['Missing required field: user_id'], ...}]
# }
```

Filter to one reason:

```python
service.inspect(max_messages=100, reason_filter=FailureReason.SCHEMA_VALIDATION)
```

---

## Replay

Pull failed events, optionally re-validate them, and re-inject the good ones
into Kinesis. Successfully replayed messages are deleted from the DLQ; events
that still fail are left in place for another pass.

```python
# Dry run first — see what would happen without touching anything
service.replay(max_messages=100, dry_run=True)
# {'replayed': 38, 'skipped': 0, 'still_failing': 0, 'dry_run': True}

# Replay only schema-validation failures after fixing the schema
result = service.replay(
    max_messages=100,
    reason_filter=FailureReason.SCHEMA_VALIDATION
)
# {'replay_id': 'replay-1759...', 'replayed': 38, 'still_failing': 0, ...}
```

### Re-validate during replay

Pass a `validator` to re-check each event before re-injecting. Events that
still fail stay in the DLQ:

```python
from streamforge import SchemaRegistry

registry = SchemaRegistry()

def is_now_valid(event):
    ok, _ = registry.validate_event('pipeline-123-events', event)
    return ok

result = service.replay(
    reason_filter=FailureReason.SCHEMA_VALIDATION,
    validator=is_now_valid
)
# {'replayed': 35, 'still_failing': 3, ...}  # 3 events still don't match schema
```

This closes the loop with the [schema registry](SCHEMA.md): fix the schema,
replay with the registry as the validator, and only genuinely-valid events flow back.

---

## Purge

Permanently delete unrecoverable failures. **Requires an explicit reason filter**
to prevent accidental full-queue data loss.

```python
# Delete malformed events that will never pass validation
service.purge(reason_filter=FailureReason.SCHEMA_VALIDATION)
# {'purged': 3, 'reason': 'schema_validation', ...}

service.purge(reason_filter=None)
# ValueError: purge requires an explicit reason_filter to prevent accidental data loss
```

---

## REST API

```bash
# Inspect
curl -X GET https://api.streamforge.com/dlq/pipeline-123/inspect \
  -H 'Content-Type: application/json' \
  -d '{"dlq_url": "...", "stream_name": "...", "max_messages": 100}'

# Replay (dry run)
curl -X POST https://api.streamforge.com/dlq/pipeline-123/replay \
  -d '{"dlq_url": "...", "stream_name": "...", "reason": "schema_validation", "dry_run": true}'

# Purge
curl -X POST https://api.streamforge.com/dlq/pipeline-123/purge \
  -d '{"dlq_url": "...", "stream_name": "...", "reason": "schema_validation"}'
```

---

## How Events Get Here

The ingestion and processing layers route failures to the DLQ with structured
metadata:

```python
# In the ingestion / processing handler
is_valid, errors = registry.validate_event(subject, event)
if not is_valid:
    sqs.send_message(
        QueueUrl=dlq_url,
        MessageBody=json.dumps({
            'pipeline_id': pipeline_id,
            'failure_reason': 'schema_validation',
            'errors': errors,
            'failed_at': datetime.utcnow().isoformat(),
            'event': event
        })
    )
    return
```

That structured body is exactly what `inspect` and `replay` read back.

---

## Batching Details

- **SQS receive** caps at 10 messages per call; the service paginates up to `max_messages`.
- **SQS delete** batches at 10 per call.
- **Kinesis put_records** batches at 500 records per call.

All limits are handled internally — callers just pass `max_messages`.

---

## CDK Deployment

```typescript
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as lambda from 'aws-cdk-lib/aws-lambda';

// DLQ with 14-day retention so failures aren't lost before replay
const dlq = new sqs.Queue(this, 'PipelineDLQ', {
  retentionPeriod: cdk.Duration.days(14),
  visibilityTimeout: cdk.Duration.seconds(60)
});

const replayFn = new lambda.Function(this, 'DLQReplay', {
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'replay.lambda_handler',
  code: lambda.Code.fromAsset('services/dlq')
});

dlq.grantConsumeMessages(replayFn);
```

---

## Testing

```bash
pytest tests/test_dlq_replay.py -v
```

Covers inspection grouping, reason filtering, replay with re-validation,
dry-run, purge safety, SQS pagination, and malformed-message handling.

---

## Roadmap

- **Scheduled auto-replay** - Retry `downstream_timeout` failures on a backoff
- **Replay rate limiting** - Throttle replay to avoid re-triggering `throttled`
- **DLQ metrics dashboard** - Failure trends over time by reason
- **Partial-field repair** - Patch known-bad fields before replay

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
