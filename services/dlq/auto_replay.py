"""
Scheduled auto-replay for StreamForge dead-letter queues.

Some failures are transient — a downstream sink timed out, or Kinesis throttled
a burst. Those should recover on their own if retried a little later. This
module runs on a schedule (EventBridge), decides which dead-lettered events are
worth retrying, and replays only those, backing off between attempts so a
still-unhealthy downstream isn't hammered.

Permanent failures (schema validation, transform errors) are never auto-retried
— they need a human/code fix first — so they stay in the DLQ for manual replay.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import boto3
from aws_lambda_powertools import Logger

from .replay import DLQReplayService, FailureReason

logger = Logger()

dynamodb = boto3.resource('dynamodb')

# Only transient failures are eligible for automatic retry.
RETRYABLE_REASONS = {
    FailureReason.DOWNSTREAM_TIMEOUT,
    FailureReason.THROTTLED,
}

# Exponential backoff schedule (minutes) indexed by attempt number.
# attempt 1 -> wait 1m, 2 -> 5m, 3 -> 15m, 4 -> 60m. After that, give up.
BACKOFF_MINUTES = [1, 5, 15, 60]
MAX_ATTEMPTS = len(BACKOFF_MINUTES)


class AutoReplayScheduler:
    """Decides when transient DLQ failures should be auto-retried, and does it."""

    def __init__(self, dlq_url: str, stream_name: str):
        self.dlq_url = dlq_url
        self.stream_name = stream_name
        self.replay_service = DLQReplayService(dlq_url, stream_name)
        self.attempts_table = dynamodb.Table('streamforge-auto-replay-attempts')

    def is_retryable(self, reason: str) -> bool:
        """Whether a failure reason is eligible for automatic retry."""
        try:
            return FailureReason(reason) in RETRYABLE_REASONS
        except ValueError:
            return False

    def backoff_due(self, attempt: int, last_attempt_at: Optional[str], now: Optional[datetime] = None) -> bool:
        """
        Whether enough time has passed since the last attempt to retry again.

        Args:
            attempt: Number of attempts already made (0 means never tried)
            last_attempt_at: ISO timestamp of the last attempt, or None
            now: Current time (injectable for testing)

        Returns:
            True if the backoff window has elapsed and another attempt is allowed
        """
        if attempt >= MAX_ATTEMPTS:
            return False

        if attempt == 0 or not last_attempt_at:
            return True

        now = now or datetime.utcnow()
        wait_minutes = BACKOFF_MINUTES[min(attempt, MAX_ATTEMPTS - 1)]
        next_due = datetime.fromisoformat(last_attempt_at) + timedelta(minutes=wait_minutes)
        return now >= next_due

    def _get_attempt_record(self, pipeline_id: str) -> Dict[str, Any]:
        """Fetch the auto-replay attempt record for a pipeline."""
        response = self.attempts_table.get_item(Key={'pipeline_id': pipeline_id})
        return response.get('Item') or {
            'pipeline_id': pipeline_id,
            'attempt': 0,
            'last_attempt_at': None
        }

    def _save_attempt_record(self, pipeline_id: str, attempt: int, replayed: int, still_failing: int):
        """Persist the latest attempt state."""
        self.attempts_table.put_item(Item={
            'pipeline_id': pipeline_id,
            'attempt': attempt,
            'last_attempt_at': datetime.utcnow().isoformat(),
            'last_replayed': replayed,
            'last_still_failing': still_failing
        })

    def _reset_attempts(self, pipeline_id: str):
        """Reset the backoff counter once the DLQ is drained of retryable failures."""
        self.attempts_table.put_item(Item={
            'pipeline_id': pipeline_id,
            'attempt': 0,
            'last_attempt_at': None
        })

    def run(self, pipeline_id: str, now: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Execute one scheduled auto-replay tick for a pipeline.

        Checks backoff state, replays retryable failures if due, updates attempt
        tracking, and reports what happened.

        Returns:
            Result describing the action taken
        """
        now = now or datetime.utcnow()
        record = self._get_attempt_record(pipeline_id)
        attempt = int(record.get('attempt', 0))
        last_attempt_at = record.get('last_attempt_at')

        if attempt >= MAX_ATTEMPTS:
            return {
                'pipeline_id': pipeline_id,
                'action': 'exhausted',
                'attempt': attempt,
                'message': f'Max auto-replay attempts ({MAX_ATTEMPTS}) reached; manual intervention required'
            }

        if not self.backoff_due(attempt, last_attempt_at, now):
            wait_minutes = BACKOFF_MINUTES[min(attempt, MAX_ATTEMPTS - 1)]
            return {
                'pipeline_id': pipeline_id,
                'action': 'waiting',
                'attempt': attempt,
                'message': f'Backoff window not elapsed (waiting {wait_minutes}m since last attempt)'
            }

        # Replay only transient, retryable failures. We run one replay per
        # retryable reason so a reason filter is applied (replay itself skips
        # non-matching messages).
        total_replayed = 0
        total_still_failing = 0

        for reason in RETRYABLE_REASONS:
            result = self.replay_service.replay(
                max_messages=100,
                reason_filter=reason
            )
            total_replayed += result['replayed']
            total_still_failing += result['still_failing']

        if total_replayed == 0 and total_still_failing == 0:
            # Nothing retryable left — reset backoff so future failures start fresh.
            self._reset_attempts(pipeline_id)
            return {
                'pipeline_id': pipeline_id,
                'action': 'idle',
                'attempt': attempt,
                'replayed': 0,
                'message': 'No retryable failures in DLQ'
            }

        new_attempt = attempt + 1
        self._save_attempt_record(pipeline_id, new_attempt, total_replayed, total_still_failing)

        return {
            'pipeline_id': pipeline_id,
            'action': 'replayed',
            'attempt': new_attempt,
            'replayed': total_replayed,
            'still_failing': total_still_failing,
            'message': f'Auto-replayed {total_replayed} event(s) on attempt {new_attempt}'
        }


# Lambda handler
def lambda_handler(event, context):
    """
    EventBridge-triggered handler for scheduled auto-replay.

    Expects event with: pipeline_id, dlq_url, stream_name.
    Configure an EventBridge rule (e.g. rate(1 minute)) per pipeline, or fan out
    over a list of pipelines.
    """
    pipeline_id = event.get('pipeline_id')
    dlq_url = event.get('dlq_url')
    stream_name = event.get('stream_name')

    if not all([pipeline_id, dlq_url, stream_name]):
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'pipeline_id, dlq_url, and stream_name are required'})
        }

    try:
        scheduler = AutoReplayScheduler(dlq_url, stream_name)
        result = scheduler.run(pipeline_id)
        return {
            'statusCode': 200,
            'body': json.dumps(result),
            'headers': {'Content-Type': 'application/json'}
        }
    except Exception as e:
        logger.error(f"Auto-replay error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
