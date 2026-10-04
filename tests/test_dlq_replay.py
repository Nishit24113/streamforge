"""
Tests for the DLQ replay service.

Boto3 clients are patched at import time; each test injects fake SQS/Kinesis
behavior so the batching, filtering, and replay logic can be exercised without AWS.
"""

import sys
import json
import pytest
from unittest.mock import MagicMock, patch

# Stub aws_lambda_powertools so the module imports without the Lambda runtime dep
if 'aws_lambda_powertools' not in sys.modules:
    powertools_stub = MagicMock()
    powertools_stub.Logger = MagicMock(return_value=MagicMock())
    sys.modules['aws_lambda_powertools'] = powertools_stub


@pytest.fixture
def mocked_clients():
    with patch('boto3.client') as client, patch('boto3.resource') as resource:
        sqs = MagicMock()
        kinesis = MagicMock()
        kinesis.put_records.return_value = {'FailedRecordCount': 0}

        def client_factory(name, *args, **kwargs):
            return {'sqs': sqs, 'kinesis': kinesis}.get(name, MagicMock())

        client.side_effect = client_factory

        table = MagicMock()
        resource.return_value.Table.return_value = table

        import importlib
        import services.dlq.replay as mod
        importlib.reload(mod)
        # Rebind module-level clients to our mocks after reload
        mod.sqs = sqs
        mod.kinesis = kinesis
        mod.dynamodb = resource.return_value

        yield mod, sqs, kinesis, table


def _dlq_message(message_id, pipeline_id, reason, event, receipt='rh'):
    return {
        'MessageId': message_id,
        'ReceiptHandle': receipt,
        'Body': json.dumps({
            'pipeline_id': pipeline_id,
            'failure_reason': reason,
            'errors': ['boom'],
            'failed_at': '2026-10-04T00:00:00Z',
            'event': event,
        }),
    }


def _queue_batches(sqs, batches):
    """Program sqs.receive_message to return each batch in turn, then empty."""
    responses = [{'Messages': b} for b in batches] + [{'Messages': []}]
    sqs.receive_message.side_effect = responses


# ---------------------------------------------------------------------------
# Inspect
# ---------------------------------------------------------------------------

def test_inspect_groups_by_reason(mocked_clients):
    mod, sqs, kinesis, table = mocked_clients
    _queue_batches(sqs, [[
        _dlq_message('m1', 'p1', 'schema_validation', {'id': '1'}, 'r1'),
        _dlq_message('m2', 'p1', 'schema_validation', {'id': '2'}, 'r2'),
        _dlq_message('m3', 'p1', 'transform_error', {'id': '3'}, 'r3'),
    ]])

    service = mod.DLQReplayService('dlq-url', 'stream')
    result = service.inspect(max_messages=10)

    assert result['total_inspected'] == 3
    assert result['by_reason']['schema_validation'] == 2
    assert result['by_reason']['transform_error'] == 1
    assert len(result['samples']) == 3


def test_inspect_reason_filter(mocked_clients):
    mod, sqs, kinesis, table = mocked_clients
    _queue_batches(sqs, [[
        _dlq_message('m1', 'p1', 'schema_validation', {'id': '1'}, 'r1'),
        _dlq_message('m2', 'p1', 'transform_error', {'id': '2'}, 'r2'),
    ]])

    service = mod.DLQReplayService('dlq-url', 'stream')
    result = service.inspect(max_messages=10, reason_filter=mod.FailureReason.SCHEMA_VALIDATION)

    assert result['by_reason'] == {'schema_validation': 1}


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

def test_replay_sends_to_kinesis_and_deletes(mocked_clients):
    mod, sqs, kinesis, table = mocked_clients
    _queue_batches(sqs, [[
        _dlq_message('m1', 'p1', 'schema_validation', {'id': '1'}, 'r1'),
        _dlq_message('m2', 'p1', 'schema_validation', {'id': '2'}, 'r2'),
    ]])

    service = mod.DLQReplayService('dlq-url', 'stream')
    result = service.replay(max_messages=10)

    assert result['replayed'] == 2
    assert result['still_failing'] == 0
    kinesis.put_records.assert_called_once()
    sent = kinesis.put_records.call_args.kwargs['Records']
    assert len(sent) == 2
    sqs.delete_message_batch.assert_called_once()


def test_replay_dry_run_does_not_send(mocked_clients):
    mod, sqs, kinesis, table = mocked_clients
    _queue_batches(sqs, [[
        _dlq_message('m1', 'p1', 'schema_validation', {'id': '1'}, 'r1'),
    ]])

    service = mod.DLQReplayService('dlq-url', 'stream')
    result = service.replay(max_messages=10, dry_run=True)

    assert result['replayed'] == 1
    assert result['dry_run'] is True
    kinesis.put_records.assert_not_called()
    sqs.delete_message_batch.assert_not_called()


def test_replay_validator_leaves_still_failing_events(mocked_clients):
    mod, sqs, kinesis, table = mocked_clients
    _queue_batches(sqs, [[
        _dlq_message('m1', 'p1', 'schema_validation', {'id': '1'}, 'r1'),
        _dlq_message('m2', 'p1', 'schema_validation', {}, 'r2'),  # missing id
    ]])

    service = mod.DLQReplayService('dlq-url', 'stream')
    # Validator passes only if the event has an 'id'
    result = service.replay(max_messages=10, validator=lambda e: 'id' in e)

    assert result['replayed'] == 1
    assert result['still_failing'] == 1
    sent = kinesis.put_records.call_args.kwargs['Records']
    assert len(sent) == 1


def test_replay_reason_filter_skips_others(mocked_clients):
    mod, sqs, kinesis, table = mocked_clients
    _queue_batches(sqs, [[
        _dlq_message('m1', 'p1', 'schema_validation', {'id': '1'}, 'r1'),
        _dlq_message('m2', 'p1', 'transform_error', {'id': '2'}, 'r2'),
    ]])

    service = mod.DLQReplayService('dlq-url', 'stream')
    result = service.replay(max_messages=10, reason_filter=mod.FailureReason.SCHEMA_VALIDATION)

    assert result['replayed'] == 1
    assert result['skipped'] == 1


# ---------------------------------------------------------------------------
# Purge
# ---------------------------------------------------------------------------

def test_purge_requires_reason(mocked_clients):
    mod, sqs, kinesis, table = mocked_clients
    service = mod.DLQReplayService('dlq-url', 'stream')
    with pytest.raises(ValueError):
        service.purge(reason_filter=None)


def test_purge_deletes_matching_reason(mocked_clients):
    mod, sqs, kinesis, table = mocked_clients
    _queue_batches(sqs, [[
        _dlq_message('m1', 'p1', 'schema_validation', {'id': '1'}, 'r1'),
        _dlq_message('m2', 'p1', 'transform_error', {'id': '2'}, 'r2'),
    ]])

    service = mod.DLQReplayService('dlq-url', 'stream')
    result = service.purge(reason_filter=mod.FailureReason.SCHEMA_VALIDATION)

    assert result['purged'] == 1
    sqs.delete_message_batch.assert_called_once()


# ---------------------------------------------------------------------------
# Batching / malformed input
# ---------------------------------------------------------------------------

def test_receive_paginates_across_batches(mocked_clients):
    mod, sqs, kinesis, table = mocked_clients
    batch1 = [_dlq_message(f'a{i}', 'p1', 'schema_validation', {'id': i}, f'r{i}') for i in range(10)]
    batch2 = [_dlq_message(f'b{i}', 'p1', 'schema_validation', {'id': i}, f'rb{i}') for i in range(5)]
    _queue_batches(sqs, [batch1, batch2])

    service = mod.DLQReplayService('dlq-url', 'stream')
    result = service.inspect(max_messages=20)

    assert result['total_inspected'] == 15


def test_malformed_body_treated_as_unknown(mocked_clients):
    mod, sqs, kinesis, table = mocked_clients
    _queue_batches(sqs, [[{'MessageId': 'm1', 'ReceiptHandle': 'r1', 'Body': 'not-json'}]])

    service = mod.DLQReplayService('dlq-url', 'stream')
    result = service.inspect(max_messages=10)

    assert result['by_reason'].get('unknown') == 1
