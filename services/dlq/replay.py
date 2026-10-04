"""
Dead-Letter Queue (DLQ) replay service for StreamForge.

When events fail processing — schema validation errors, transform exceptions,
downstream timeouts — they land in a DLQ instead of being dropped. This service
lets operators inspect those failures and replay them back into the pipeline
after the root cause is fixed.
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
import boto3
from aws_lambda_powertools import Logger

logger = Logger()

sqs = boto3.client('sqs')
kinesis = boto3.client('kinesis')
dynamodb = boto3.resource('dynamodb')


class FailureReason(Enum):
    """Why an event landed in the DLQ."""
    SCHEMA_VALIDATION = "schema_validation"
    TRANSFORM_ERROR = "transform_error"
    DOWNSTREAM_TIMEOUT = "downstream_timeout"
    THROTTLED = "throttled"
    UNKNOWN = "unknown"


class DLQReplayService:
    """Inspects and replays events from a pipeline's dead-letter queue."""

    def __init__(self, dlq_url: str, stream_name: str):
        self.dlq_url = dlq_url
        self.stream_name = stream_name
        self.replay_table = dynamodb.Table('streamforge-dlq-replays')

    def inspect(
        self,
        max_messages: int = 100,
        reason_filter: Optional[FailureReason] = None
    ) -> Dict[str, Any]:
        """
        Peek at messages in the DLQ without removing them.

        Uses SQS visibility timeout so inspected messages return to the queue.

        Args:
            max_messages: Maximum number of messages to inspect
            reason_filter: Only return messages with this failure reason

        Returns:
            Summary of failures grouped by reason, plus sample messages
        """
        messages = self._peek_messages(max_messages)

        by_reason: Dict[str, int] = {}
        samples: List[Dict[str, Any]] = []

        for msg in messages:
            body = self._parse_body(msg)
            reason = body.get('failure_reason', FailureReason.UNKNOWN.value)

            if reason_filter and reason != reason_filter.value:
                continue

            by_reason[reason] = by_reason.get(reason, 0) + 1

            if len(samples) < 10:
                samples.append({
                    'message_id': msg.get('MessageId'),
                    'pipeline_id': body.get('pipeline_id'),
                    'failure_reason': reason,
                    'errors': body.get('errors', []),
                    'failed_at': body.get('failed_at'),
                    'event_preview': self._truncate(body.get('event', {}))
                })

        return {
            'total_inspected': len(messages),
            'by_reason': by_reason,
            'samples': samples
        }

    def replay(
        self,
        max_messages: int = 100,
        reason_filter: Optional[FailureReason] = None,
        validator: Optional[Callable[[Dict[str, Any]], bool]] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Replay failed events back into the pipeline.

        Pulls messages from the DLQ, optionally re-validates them, and re-injects
        valid events into the Kinesis stream. Successfully replayed messages are
        deleted from the DLQ; events that still fail are left in place.

        Args:
            max_messages: Maximum number of messages to replay
            reason_filter: Only replay messages with this failure reason
            validator: Optional callable that returns True if an event is now valid
            dry_run: If True, report what would be replayed without doing it

        Returns:
            Replay result with counts and any remaining failures
        """
        replay_id = f"replay-{int(datetime.utcnow().timestamp() * 1000)}"
        messages = self._receive_messages(max_messages)

        replayed = 0
        skipped = 0
        still_failing = 0
        records_to_send: List[Dict[str, Any]] = []
        delete_entries: List[Dict[str, str]] = []

        for msg in messages:
            body = self._parse_body(msg)
            reason = body.get('failure_reason', FailureReason.UNKNOWN.value)
            event = body.get('event', {})

            if reason_filter and reason != reason_filter.value:
                skipped += 1
                continue

            # Re-validate if a validator is provided (e.g. after a schema fix)
            if validator is not None and not validator(event):
                still_failing += 1
                continue

            if dry_run:
                replayed += 1
                continue

            records_to_send.append({
                'Data': json.dumps(event).encode('utf-8'),
                'PartitionKey': body.get('pipeline_id', 'default')
            })
            delete_entries.append({
                'Id': str(len(delete_entries)),
                'ReceiptHandle': msg['ReceiptHandle']
            })
            replayed += 1

        if not dry_run and records_to_send:
            self._send_to_stream(records_to_send)
            self._delete_messages(delete_entries)

        result = {
            'replay_id': replay_id,
            'replayed': replayed,
            'skipped': skipped,
            'still_failing': still_failing,
            'dry_run': dry_run,
            'timestamp': datetime.utcnow().isoformat()
        }

        if not dry_run:
            self.replay_table.put_item(Item=result)

        logger.info(f"Replay {replay_id}: {replayed} replayed, {still_failing} still failing")
        return result

    def purge(self, reason_filter: Optional[FailureReason] = None, max_messages: int = 100) -> Dict[str, Any]:
        """
        Permanently delete messages from the DLQ.

        Use when failures are known to be unrecoverable (e.g. malformed events
        that will never pass validation). Requires an explicit reason filter to
        avoid accidental full purges.

        Args:
            reason_filter: Only purge messages with this failure reason (required)
            max_messages: Maximum number of messages to purge

        Returns:
            Purge result with count deleted
        """
        if reason_filter is None:
            raise ValueError("purge requires an explicit reason_filter to prevent accidental data loss")

        messages = self._receive_messages(max_messages)
        delete_entries: List[Dict[str, str]] = []

        for msg in messages:
            body = self._parse_body(msg)
            reason = body.get('failure_reason', FailureReason.UNKNOWN.value)

            if reason == reason_filter.value:
                delete_entries.append({
                    'Id': str(len(delete_entries)),
                    'ReceiptHandle': msg['ReceiptHandle']
                })

        if delete_entries:
            self._delete_messages(delete_entries)

        return {
            'purged': len(delete_entries),
            'reason': reason_filter.value,
            'timestamp': datetime.utcnow().isoformat()
        }

    # ------------------------------------------------------------------
    # SQS / Kinesis helpers
    # ------------------------------------------------------------------

    def _peek_messages(self, max_messages: int) -> List[Dict[str, Any]]:
        """Receive messages with a short visibility timeout so they return quickly."""
        return self._receive_messages(max_messages, visibility_timeout=5)

    def _receive_messages(
        self,
        max_messages: int,
        visibility_timeout: int = 60
    ) -> List[Dict[str, Any]]:
        """Receive up to max_messages from the DLQ (SQS caps each call at 10)."""
        collected: List[Dict[str, Any]] = []

        while len(collected) < max_messages:
            batch_size = min(10, max_messages - len(collected))
            response = sqs.receive_message(
                QueueUrl=self.dlq_url,
                MaxNumberOfMessages=batch_size,
                VisibilityTimeout=visibility_timeout,
                WaitTimeSeconds=1,
                AttributeNames=['All']
            )
            batch = response.get('Messages', [])
            if not batch:
                break
            collected.extend(batch)

        return collected

    def _send_to_stream(self, records: List[Dict[str, Any]]):
        """Re-inject records into Kinesis in batches of 500 (the API limit)."""
        for i in range(0, len(records), 500):
            chunk = records[i:i + 500]
            response = kinesis.put_records(
                StreamName=self.stream_name,
                Records=chunk
            )
            failed = response.get('FailedRecordCount', 0)
            if failed:
                logger.warning(f"{failed} records failed to re-inject into {self.stream_name}")

    def _delete_messages(self, entries: List[Dict[str, str]]):
        """Delete messages from the DLQ in batches of 10 (the SQS limit)."""
        for i in range(0, len(entries), 10):
            chunk = entries[i:i + 10]
            # Re-number Ids within the batch to keep them unique per call
            for idx, entry in enumerate(chunk):
                entry['Id'] = str(idx)
            sqs.delete_message_batch(QueueUrl=self.dlq_url, Entries=chunk)

    @staticmethod
    def _parse_body(msg: Dict[str, Any]) -> Dict[str, Any]:
        """Parse an SQS message body, tolerating malformed JSON."""
        try:
            return json.loads(msg.get('Body', '{}'))
        except (json.JSONDecodeError, TypeError):
            return {'failure_reason': FailureReason.UNKNOWN.value, 'event': {}}

    @staticmethod
    def _truncate(event: Dict[str, Any], max_len: int = 200) -> str:
        """Truncate an event preview so inspection responses stay small."""
        preview = json.dumps(event)
        return preview if len(preview) <= max_len else preview[:max_len] + '...'


# Lambda handler
def lambda_handler(event, context):
    """
    Lambda handler for DLQ replay API.

    Endpoints:
    - GET  /dlq/{pipeline_id}/inspect  - Inspect failures grouped by reason
    - POST /dlq/{pipeline_id}/replay   - Replay failed events
    - POST /dlq/{pipeline_id}/purge    - Permanently delete failures (requires reason)
    """
    path = event.get('path', '')
    method = event.get('httpMethod', 'GET')
    path_params = event.get('pathParameters', {}) or {}
    body = json.loads(event.get('body', '{}')) if event.get('body') else {}

    dlq_url = body.get('dlq_url') or event.get('dlq_url')
    stream_name = body.get('stream_name') or event.get('stream_name')

    if not dlq_url or not stream_name:
        return _response(400, {'error': 'dlq_url and stream_name are required'})

    service = DLQReplayService(dlq_url, stream_name)
    reason = FailureReason(body['reason']) if body.get('reason') else None

    try:
        if path.endswith('/inspect'):
            result = service.inspect(
                max_messages=int(body.get('max_messages', 100)),
                reason_filter=reason
            )
            return _response(200, result)

        elif path.endswith('/replay') and method == 'POST':
            result = service.replay(
                max_messages=int(body.get('max_messages', 100)),
                reason_filter=reason,
                dry_run=bool(body.get('dry_run', False))
            )
            return _response(200, result)

        elif path.endswith('/purge') and method == 'POST':
            result = service.purge(reason_filter=reason)
            return _response(200, result)

        else:
            return _response(404, {'error': 'Not found'})

    except ValueError as e:
        return _response(400, {'error': str(e)})
    except Exception as e:
        logger.error(f"DLQ replay error: {e}")
        return _response(500, {'error': str(e)})


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status_code,
        'body': json.dumps(body),
        'headers': {'Content-Type': 'application/json'}
    }
