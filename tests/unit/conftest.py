import json
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.update({
    'KINESIS_STREAM': 'test-stream',
    'PIPELINE_TABLE': 'test-pipelines',
    'RUN_HISTORY_TABLE': 'test-runs',
    'DATA_LAKE_BUCKET': 'test-bucket',
    'ALERTS_TABLE': 'test-alerts',
    'DLQ_URL': 'https://sqs.us-west-2.amazonaws.com/000/test-dlq',
    'STATE_MACHINE_ARN': 'arn:aws:states:us-west-2:000:stateMachine:test',
    'ATHENA_WORKGROUP': 'test-workgroup',
    'ATHENA_DATABASE': 'test-db',
    'AWS_DEFAULT_REGION': 'us-west-2',
})


@pytest.fixture
def mock_kinesis():
    with patch('boto3.client') as m:
        client = MagicMock()
        client.put_records.return_value = {'FailedRecordCount': 0}
        m.return_value = client
        yield client


@pytest.fixture
def mock_dynamodb():
    with patch('boto3.resource') as m:
        resource = MagicMock()
        table = MagicMock()
        table.put_item.return_value = {}
        table.get_item.return_value = {'Item': None}
        table.scan.return_value = {'Items': [], 'Count': 0}
        table.query.return_value = {'Items': [], 'Count': 0}
        table.update_item.return_value = {}
        resource.Table.return_value = table
        m.return_value = resource
        yield table


@pytest.fixture
def mock_s3():
    with patch('boto3.client') as m:
        client = MagicMock()
        client.put_object.return_value = {}
        client.generate_presigned_url.return_value = 'https://s3.amazonaws.com/test'
        m.return_value = client
        yield client


@pytest.fixture
def api_event():
    def _make(method='GET', path='/', body=None, headers=None, path_params=None, query_params=None):
        return {
            'httpMethod': method,
            'path': path,
            'body': json.dumps(body) if body else None,
            'headers': headers or {},
            'pathParameters': path_params,
            'queryStringParameters': query_params,
        }
    return _make


@pytest.fixture
def pipeline_event():
    def _make(**kwargs):
        base = {
            'pipeline_id': 'test-pipeline',
            'run_id': 'run-abc123',
            'raw_location': 's3://test-bucket/raw/test-pipeline/run-abc123.json',
            'events_count': 5,
            'pipeline_config': {'steps': []},
        }
        base.update(kwargs)
        return base
    return _make


@pytest.fixture
def sample_events():
    return [
        {
            'event_id': f'evt-{i}',
            'pipeline_id': 'test-pipeline',
            'timestamp': 1700000000000 + i * 1000,
            'source': 'api',
            'event_type': 'purchase',
            'payload': json.dumps({'amount': 10 + i * 5, 'user': f'user-{i}'}),
        }
        for i in range(10)
    ]
