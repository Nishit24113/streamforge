import json
import math
import pytest
from unittest.mock import MagicMock, patch, ANY


# ---------------------------------------------------------------------------
# API Handler tests
# ---------------------------------------------------------------------------

class TestApiHandler:

    def _import_handler(self):
        import importlib
        import services.ingestion.api_handler_module as mod
        return mod

    @pytest.fixture(autouse=True)
    def setup(self):
        self.kinesis = MagicMock()
        self.kinesis.put_records.return_value = {'FailedRecordCount': 0}
        self.s3 = MagicMock()
        self.s3.generate_presigned_url.return_value = 'https://presigned.test/upload'
        self.dynamodb = MagicMock()
        self.pipeline_table = MagicMock()
        self.run_table = MagicMock()
        self.dynamodb.Table.side_effect = lambda name: {
            'test-pipelines': self.pipeline_table,
            'test-runs': self.run_table,
            'streamforge-pipelines': self.pipeline_table,
            'streamforge-runs': self.run_table,
        }.get(name, MagicMock())

        patches = [
            patch('boto3.client', side_effect=lambda svc, **kw: {
                'kinesis': self.kinesis, 's3': self.s3, 'sqs': MagicMock(),
            }.get(svc, MagicMock())),
            patch('boto3.resource', return_value=self.dynamodb),
        ]
        for p in patches:
            p.start()

        import importlib
        if 'services.ingestion.api-handler.handler' in __import__('sys').modules:
            del __import__('sys').modules['services.ingestion.api-handler.handler']

        import sys
        sys.path.insert(0, 'services/ingestion/api-handler')
        import handler as api_handler
        self.handler = api_handler

        yield
        for p in patches:
            p.stop()

    def _event(self, method='GET', path='/', body=None, headers=None, path_params=None):
        return {
            'httpMethod': method,
            'path': path,
            'body': json.dumps(body) if body else None,
            'headers': headers or {},
            'pathParameters': path_params,
        }

    def test_health_endpoint(self):
        result = self.handler.lambda_handler(
            self._event('GET', '/v1/health'), None
        )
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['status'] == 'healthy'
        assert body['service'] == 'streamforge-ingestion'
        assert 'timestamp' in body

    def test_health_cors_headers(self):
        result = self.handler.lambda_handler(
            self._event('GET', '/v1/health'), None
        )
        assert result['headers']['Access-Control-Allow-Origin'] == '*'
        assert 'X-Org-Id' in result['headers']['Access-Control-Allow-Headers']

    def test_ingest_accepts_events(self):
        events = [{'user': 'test', 'action': 'click'}]
        result = self.handler.lambda_handler(
            self._event('POST', '/v1/ingest', {'pipeline': 'p1', 'events': events}),
            None
        )
        assert result['statusCode'] == 202
        body = json.loads(result['body'])
        assert body['status'] == 'accepted'
        assert body['events_received'] == 1
        self.kinesis.put_records.assert_called_once()

    def test_ingest_rejects_empty_events(self):
        result = self.handler.lambda_handler(
            self._event('POST', '/v1/ingest', {'pipeline': 'p1', 'events': []}),
            None
        )
        assert result['statusCode'] == 400

    def test_ingest_rejects_over_500_events(self):
        events = [{'i': i} for i in range(501)]
        result = self.handler.lambda_handler(
            self._event('POST', '/v1/ingest', {'pipeline': 'p1', 'events': events}),
            None
        )
        assert result['statusCode'] == 400
        assert '500' in json.loads(result['body'])['error']

    def test_ingest_batches_kinesis_records(self):
        events = [{'i': i} for i in range(150)]
        self.handler.lambda_handler(
            self._event('POST', '/v1/ingest', {'pipeline': 'p1', 'events': events}),
            None
        )
        assert self.kinesis.put_records.call_count == 2

    def test_ingest_with_org_id(self):
        events = [{'x': 1}]
        result = self.handler.lambda_handler(
            self._event('POST', '/v1/ingest', {'pipeline': 'p1', 'events': events},
                        headers={'X-Org-Id': 'org-42'}),
            None
        )
        assert result['statusCode'] == 202
        call_args = self.kinesis.put_records.call_args
        record_data = json.loads(call_args[1]['Records'][0]['Data'].decode())
        assert record_data['org_id'] == 'org-42'

    def test_ingest_null_body(self):
        event = self._event('POST', '/v1/ingest')
        event['body'] = None
        result = self.handler.lambda_handler(event, None)
        assert result['statusCode'] == 400

    def test_upload_returns_presigned_url(self):
        result = self.handler.lambda_handler(
            self._event('POST', '/v1/upload', {'pipeline': 'p1', 'filename': 'data.csv'}),
            None
        )
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'upload_url' in body
        assert body['pipeline'] == 'p1'

    def test_upload_includes_org_in_key(self):
        self.handler.lambda_handler(
            self._event('POST', '/v1/upload',
                        {'pipeline': 'p1'},
                        headers={'X-Org-Id': 'org-99'}),
            None
        )
        call_args = self.s3.generate_presigned_url.call_args
        key = call_args[1]['Params']['Key']
        assert 'org-99' in key

    def test_list_pipelines(self):
        self.pipeline_table.scan.return_value = {
            'Items': [{'pipeline_id': 'p1', 'name': 'Pipeline 1'}],
            'Count': 1,
        }
        result = self.handler.lambda_handler(
            self._event('GET', '/v1/pipelines'), None
        )
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['count'] == 1

    def test_create_pipeline(self):
        result = self.handler.lambda_handler(
            self._event('POST', '/v1/pipelines', {
                'name': 'test', 'steps': [{'type': 'validate'}]
            }),
            None
        )
        assert result['statusCode'] == 201
        body = json.loads(result['body'])
        assert body['status'] == 'created'
        assert body['pipeline']['status'] == 'ACTIVE'
        self.pipeline_table.put_item.assert_called_once()

    def test_get_pipeline_not_found(self):
        self.pipeline_table.get_item.return_value = {'Item': None}
        result = self.handler.lambda_handler(
            self._event('GET', '/v1/pipelines/missing', path_params={'pipeline_id': 'missing'}),
            None
        )
        assert result['statusCode'] == 404

    def test_get_pipeline_found(self):
        self.pipeline_table.get_item.return_value = {
            'Item': {'pipeline_id': 'p1', 'name': 'Test'}
        }
        result = self.handler.lambda_handler(
            self._event('GET', '/v1/pipelines/p1', path_params={'pipeline_id': 'p1'}),
            None
        )
        assert result['statusCode'] == 200

    def test_get_runs(self):
        self.run_table.query.return_value = {
            'Items': [{'run_id': 'r1', 'status': 'COMPLETED'}],
            'Count': 1,
        }
        result = self.handler.lambda_handler(
            self._event('GET', '/v1/pipelines/p1/runs',
                        path_params={'pipeline_id': 'p1'}),
            None
        )
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['count'] == 1

    def test_not_found_route(self):
        result = self.handler.lambda_handler(
            self._event('GET', '/v1/unknown'), None
        )
        assert result['statusCode'] == 404

    def test_get_org_id_defaults(self):
        assert self.handler.get_org_id({}) == 'default'
        assert self.handler.get_org_id({'headers': None}) == 'default'
        assert self.handler.get_org_id({'headers': {'X-Org-Id': 'a'}}) == 'a'
        assert self.handler.get_org_id({'headers': {'x-org-id': 'b'}}) == 'b'


# ---------------------------------------------------------------------------
# Transformer tests (pure logic — no AWS mocking needed for operations)
# ---------------------------------------------------------------------------

class TestTransformerOperations:

    @pytest.fixture(autouse=True)
    def setup(self):
        patches = [
            patch('boto3.client', return_value=MagicMock()),
            patch('boto3.resource', return_value=MagicMock()),
        ]
        for p in patches:
            p.start()

        import sys
        sys.path.insert(0, 'services/processing/transformer')
        import handler as transformer
        self.handler = transformer

        yield
        for p in patches:
            p.stop()

    def test_op_rename(self):
        record = {'old_name': 'value'}
        result = self.handler.op_rename(record, {'from': 'old_name', 'to': 'new_name'})
        assert 'new_name' in result
        assert 'old_name' not in result

    def test_op_rename_missing_field(self):
        record = {'other': 'value'}
        result = self.handler.op_rename(record, {'from': 'missing', 'to': 'new'})
        assert result == {'other': 'value'}

    def test_op_add_field_static(self):
        record = {}
        result = self.handler.op_add_field(record, {'name': 'region', 'value': 'us-west-2'})
        assert result['region'] == 'us-west-2'

    def test_op_add_field_now(self):
        record = {}
        result = self.handler.op_add_field(record, {'name': 'ts', 'value': '$NOW'})
        assert isinstance(result['ts'], int)

    def test_op_add_field_uuid(self):
        record = {}
        result = self.handler.op_add_field(record, {'name': 'id', 'value': '$UUID'})
        assert len(result['id']) == 36

    def test_op_remove_field(self):
        record = {'a': 1, 'b': 2}
        result = self.handler.op_remove_field(record, {'field': 'a'})
        assert 'a' not in result
        assert result['b'] == 2

    def test_op_remove_missing_field(self):
        record = {'a': 1}
        result = self.handler.op_remove_field(record, {'field': 'missing'})
        assert result == {'a': 1}

    def test_op_cast_to_int(self):
        record = {'val': '42.7'}
        result = self.handler.op_cast(record, {'field': 'val', 'to': 'int'})
        assert result['val'] == 42

    def test_op_cast_to_float(self):
        record = {'val': '3.14'}
        result = self.handler.op_cast(record, {'field': 'val', 'to': 'float'})
        assert result['val'] == 3.14

    def test_op_cast_to_string(self):
        record = {'val': 42}
        result = self.handler.op_cast(record, {'field': 'val', 'to': 'string'})
        assert result['val'] == '42'

    def test_op_cast_to_boolean(self):
        record = {'val': 1}
        result = self.handler.op_cast(record, {'field': 'val', 'to': 'boolean'})
        assert result['val'] is True

    def test_op_flatten(self):
        record = {'meta': {'region': 'us', 'env': 'prod'}, 'id': 1}
        result = self.handler.op_flatten(record, {'field': 'meta'})
        assert result['region'] == 'us'
        assert result['env'] == 'prod'
        assert 'meta' not in result

    def test_op_flatten_with_prefix(self):
        record = {'meta': {'key': 'val'}}
        result = self.handler.op_flatten(record, {'field': 'meta', 'prefix': 'meta_'})
        assert result['meta_key'] == 'val'

    def test_op_filter_eq_pass(self):
        record = {'status': 'active'}
        result = self.handler.op_filter(record, {'field': 'status', 'operator': 'eq', 'value': 'active'})
        assert result is not None

    def test_op_filter_eq_reject(self):
        record = {'status': 'inactive'}
        result = self.handler.op_filter(record, {'field': 'status', 'operator': 'eq', 'value': 'active'})
        assert result is None

    def test_op_filter_gt(self):
        assert self.handler.op_filter({'val': 10}, {'field': 'val', 'operator': 'gt', 'value': 5}) is not None
        assert self.handler.op_filter({'val': 3}, {'field': 'val', 'operator': 'gt', 'value': 5}) is None

    def test_op_filter_lt(self):
        assert self.handler.op_filter({'val': 3}, {'field': 'val', 'operator': 'lt', 'value': 5}) is not None
        assert self.handler.op_filter({'val': 10}, {'field': 'val', 'operator': 'lt', 'value': 5}) is None

    def test_op_filter_contains(self):
        assert self.handler.op_filter({'msg': 'hello world'}, {'field': 'msg', 'operator': 'contains', 'value': 'world'}) is not None
        assert self.handler.op_filter({'msg': 'hello'}, {'field': 'msg', 'operator': 'contains', 'value': 'world'}) is None

    def test_op_filter_missing_field(self):
        result = self.handler.op_filter({}, {'field': 'missing', 'operator': 'eq', 'value': 'x'})
        assert result is not None

    def test_op_map_values(self):
        record = {'status': 'A'}
        result = self.handler.op_map_values(record, {'field': 'status', 'mapping': {'A': 'active', 'I': 'inactive'}})
        assert result['status'] == 'active'

    def test_op_map_values_no_match(self):
        record = {'status': 'X'}
        result = self.handler.op_map_values(record, {'field': 'status', 'mapping': {'A': 'active'}})
        assert result['status'] == 'X'

    def test_op_extract(self):
        record = {'data': {'name': 'test'}}
        result = self.handler.op_extract(record, {'source': 'data', 'target': 'name', 'key': 'name'})
        assert result['name'] == 'test'

    def test_op_lowercase(self):
        record = {'name': 'HELLO'}
        result = self.handler.op_lowercase(record, {'field': 'name'})
        assert result['name'] == 'hello'

    def test_op_uppercase(self):
        record = {'name': 'hello'}
        result = self.handler.op_uppercase(record, {'field': 'name'})
        assert result['name'] == 'HELLO'

    def test_op_default_sets_missing(self):
        record = {}
        result = self.handler.op_default(record, {'field': 'region', 'value': 'us-west-2'})
        assert result['region'] == 'us-west-2'

    def test_op_default_sets_none(self):
        record = {'region': None}
        result = self.handler.op_default(record, {'field': 'region', 'value': 'us-west-2'})
        assert result['region'] == 'us-west-2'

    def test_op_default_preserves_existing(self):
        record = {'region': 'eu-west-1'}
        result = self.handler.op_default(record, {'field': 'region', 'value': 'us-west-2'})
        assert result['region'] == 'eu-west-1'

    def test_op_hash_sha256(self):
        record = {'email': 'test@example.com'}
        result = self.handler.op_hash(record, {'field': 'email', 'algorithm': 'sha256'})
        assert len(result['email']) == 64
        assert result['email'] != 'test@example.com'

    def test_op_hash_md5(self):
        record = {'val': 'secret'}
        result = self.handler.op_hash(record, {'field': 'val', 'algorithm': 'md5'})
        assert len(result['val']) == 32


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------

class TestValidator:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_s3 = MagicMock()
        self.mock_dynamo = MagicMock()
        self.mock_run_table = MagicMock()
        self.mock_dynamo.Table.return_value = self.mock_run_table

        patches = [
            patch('boto3.client', return_value=self.mock_s3),
            patch('boto3.resource', return_value=self.mock_dynamo),
        ]
        for p in patches:
            p.start()

        import sys
        sys.path.insert(0, 'services/processing/validator')
        if 'handler' in sys.modules:
            del sys.modules['handler']
        import handler as validator
        self.handler = validator

        yield
        for p in patches:
            p.stop()

    def _mock_s3_events(self, events):
        body = MagicMock()
        body.read.return_value = json.dumps(events).encode()
        self.mock_s3.get_object.return_value = {'Body': body}

    def test_all_valid_events(self):
        events = [
            {'user_id': 'u1', 'amount': 10},
            {'user_id': 'u2', 'amount': 20},
        ]
        self._mock_s3_events(events)

        result = self.handler.lambda_handler({
            'pipeline_id': 'p1',
            'run_id': 'r1',
            'raw_location': 's3://test-bucket/raw/r1.json',
            'pipeline_config': {
                'steps': [{
                    'type': 'validate',
                    'schema': {'user_id': 'string', 'amount': 'number'},
                }]
            }
        }, None)

        assert result['valid_count'] == 2
        assert result['rejected_count'] == 0

    def test_type_validation_rejects_wrong_types(self):
        events = [
            {'user_id': 123, 'amount': 'not-a-number'},
        ]
        self._mock_s3_events(events)

        result = self.handler.lambda_handler({
            'pipeline_id': 'p1',
            'run_id': 'r1',
            'raw_location': 's3://test-bucket/raw/r1.json',
            'pipeline_config': {
                'steps': [{
                    'type': 'validate',
                    'schema': {'user_id': 'string', 'amount': 'number'},
                }]
            }
        }, None)

        assert result['valid_count'] == 0
        assert result['rejected_count'] == 1

    def test_null_rejection(self):
        events = [{'user_id': None, 'amount': 10}]
        self._mock_s3_events(events)

        result = self.handler.lambda_handler({
            'pipeline_id': 'p1',
            'run_id': 'r1',
            'raw_location': 's3://test-bucket/raw/r1.json',
            'pipeline_config': {
                'steps': [{
                    'type': 'validate',
                    'schema': {},
                    'reject_nulls': ['user_id'],
                }]
            }
        }, None)

        assert result['rejected_count'] == 1

    def test_range_check(self):
        events = [
            {'val': 5},
            {'val': 150},
        ]
        self._mock_s3_events(events)

        result = self.handler.lambda_handler({
            'pipeline_id': 'p1',
            'run_id': 'r1',
            'raw_location': 's3://test-bucket/raw/r1.json',
            'pipeline_config': {
                'steps': [{
                    'type': 'validate',
                    'schema': {},
                    'range_checks': {'val': {'min': 0, 'max': 100}},
                }]
            }
        }, None)

        assert result['valid_count'] == 1
        assert result['rejected_count'] == 1

    def test_no_validation_steps_passes_all(self):
        events = [{'anything': 'goes'}]
        self._mock_s3_events(events)

        result = self.handler.lambda_handler({
            'pipeline_id': 'p1',
            'run_id': 'r1',
            'raw_location': 's3://test-bucket/raw/r1.json',
            'pipeline_config': {'steps': []},
        }, None)

        assert result['valid_count'] == 1
        assert result['rejected_count'] == 0


# ---------------------------------------------------------------------------
# Anomaly Detector tests (pure algorithm logic)
# ---------------------------------------------------------------------------

class TestAnomalyDetector:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_s3 = MagicMock()
        self.mock_dynamo = MagicMock()
        self.mock_alerts_table = MagicMock()
        self.mock_run_table = MagicMock()

        def table_factory(name):
            if 'alerts' in name:
                return self.mock_alerts_table
            return self.mock_run_table

        self.mock_dynamo.Table.side_effect = table_factory

        patches = [
            patch('boto3.client', return_value=self.mock_s3),
            patch('boto3.resource', return_value=self.mock_dynamo),
        ]
        for p in patches:
            p.start()

        import sys
        sys.path.insert(0, 'services/processing/anomaly-detector')
        if 'handler' in sys.modules:
            del sys.modules['handler']
        import handler as anomaly
        self.handler = anomaly

        yield
        for p in patches:
            p.stop()

    def _make_events(self, values, field='amount'):
        return [
            {
                'event_id': f'evt-{i}',
                'pipeline_id': 'p1',
                'timestamp': 1700000000000,
                'payload': json.dumps({field: v}),
            }
            for i, v in enumerate(values)
        ]

    def test_zscore_detects_outlier(self):
        values = [10, 11, 10, 12, 10, 11, 10, 100]
        events = self._make_events(values)
        count = self.handler.detect_zscore(events, 'amount', threshold=2.0)
        assert count >= 1
        assert events[-1].get('is_anomaly') is True

    def test_zscore_no_anomalies_in_uniform(self):
        values = [10, 10, 10, 10, 10, 10, 10, 10]
        events = self._make_events(values)
        count = self.handler.detect_zscore(events, 'amount')
        assert count == 0

    def test_zscore_too_few_values(self):
        events = self._make_events([10, 20, 30])
        count = self.handler.detect_zscore(events, 'amount')
        assert count == 0

    def test_zscore_handles_none_values(self):
        values = [10, 11, None, 12, 10, 100]
        events = []
        for i, v in enumerate(values):
            payload = {'amount': v} if v is not None else {}
            events.append({
                'event_id': f'evt-{i}',
                'payload': json.dumps(payload),
            })
        count = self.handler.detect_zscore(events, 'amount', threshold=2.0)
        assert isinstance(count, int)

    def test_iqr_detects_outlier(self):
        values = list(range(10, 30)) + [500]
        events = self._make_events(values)
        count = self.handler.detect_iqr(events, 'amount')
        assert count >= 1

    def test_iqr_too_few_values(self):
        events = self._make_events([1, 2, 3])
        count = self.handler.detect_iqr(events, 'amount')
        assert count == 0

    def test_mad_detects_outlier(self):
        values = [10, 11, 10, 12, 10, 11, 10, 200]
        events = self._make_events(values)
        count = self.handler.detect_mad(events, 'amount', threshold=3.5)
        assert count >= 1

    def test_mad_zero_deviation(self):
        events = self._make_events([10, 10, 10, 10, 10])
        count = self.handler.detect_mad(events, 'amount')
        assert count == 0

    def test_isolation_forest_falls_back_on_small_data(self):
        values = list(range(10))
        events = self._make_events(values)
        count = self.handler.detect_isolation_forest(events, 'amount')
        assert isinstance(count, int)

    def test_isolation_forest_detects_on_large_data(self):
        values = [10 + (i % 5) for i in range(30)] + [1000]
        events = self._make_events(values)
        count = self.handler.detect_isolation_forest(events, 'amount', contamination=0.1)
        assert isinstance(count, int)
        assert count >= 1

    def test_get_numeric_value_from_payload_string(self):
        event = {'payload': json.dumps({'amount': 42.5})}
        assert self.handler.get_numeric_value(event, 'amount') == 42.5

    def test_get_numeric_value_from_payload_dict(self):
        event = {'payload': {'amount': 10}}
        assert self.handler.get_numeric_value(event, 'amount') == 10.0

    def test_get_numeric_value_missing_returns_none(self):
        event = {'payload': '{}'}
        assert self.handler.get_numeric_value(event, 'missing') is None

    def test_find_numeric_fields(self):
        events = [
            {'payload': json.dumps({'amount': 10, 'user': 'test', 'count': 5})}
            for _ in range(10)
        ]
        fields = self.handler.find_numeric_fields(events)
        assert 'amount' in fields
        assert 'count' in fields
        assert 'user' not in fields


# ---------------------------------------------------------------------------
# Aggregator tests
# ---------------------------------------------------------------------------

class TestAggregator:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_s3 = MagicMock()
        self.mock_dynamo = MagicMock()
        self.mock_run_table = MagicMock()
        self.mock_dynamo.Table.return_value = self.mock_run_table

        patches = [
            patch('boto3.client', return_value=self.mock_s3),
            patch('boto3.resource', return_value=self.mock_dynamo),
        ]
        for p in patches:
            p.start()

        import sys
        sys.path.insert(0, 'services/processing/aggregator')
        if 'handler' in sys.modules:
            del sys.modules['handler']
        import handler as aggregator
        self.handler = aggregator

        yield
        for p in patches:
            p.stop()

    def test_percentile_basic(self):
        assert self.handler.percentile([1, 2, 3, 4, 5], 50) == 3
        assert self.handler.percentile([], 50) == 0

    def test_percentile_p95(self):
        values = list(range(1, 101))
        p95 = self.handler.percentile(values, 95)
        assert 94 <= p95 <= 96

    def test_compute_aggregations_sum(self):
        events = [
            {'timestamp': 1700000000000, 'amount': 10},
            {'timestamp': 1700000001000, 'amount': 20},
            {'timestamp': 1700000002000, 'amount': 30},
        ]
        metrics = [{'field': 'amount', 'agg': 'sum', 'alias': 'total'}]
        result = self.handler.compute_aggregations(events, 3600, [], metrics)
        assert len(result) >= 1
        assert result[0]['total'] == 60

    def test_compute_aggregations_avg(self):
        events = [
            {'timestamp': 1700000000000, 'amount': 10},
            {'timestamp': 1700000001000, 'amount': 20},
        ]
        metrics = [{'field': 'amount', 'agg': 'avg', 'alias': 'avg_amount'}]
        result = self.handler.compute_aggregations(events, 3600, [], metrics)
        assert result[0]['avg_amount'] == 15.0

    def test_compute_aggregations_min_max(self):
        events = [
            {'timestamp': 1700000000000, 'amount': 5},
            {'timestamp': 1700000001000, 'amount': 50},
        ]
        metrics = [
            {'field': 'amount', 'agg': 'min', 'alias': 'min_a'},
            {'field': 'amount', 'agg': 'max', 'alias': 'max_a'},
        ]
        result = self.handler.compute_aggregations(events, 3600, [], metrics)
        assert result[0]['min_a'] == 5.0
        assert result[0]['max_a'] == 50.0

    def test_compute_aggregations_count_distinct(self):
        events = [
            {'timestamp': 1700000000000, 'user': 'alice'},
            {'timestamp': 1700000001000, 'user': 'bob'},
            {'timestamp': 1700000002000, 'user': 'alice'},
        ]
        metrics = [{'field': 'user', 'agg': 'count_distinct', 'alias': 'unique_users'}]
        result = self.handler.compute_aggregations(events, 3600, [], metrics)
        assert result[0]['unique_users'] == 2

    def test_compute_aggregations_stddev(self):
        events = [
            {'timestamp': 1700000000000, 'val': 10},
            {'timestamp': 1700000001000, 'val': 20},
            {'timestamp': 1700000002000, 'val': 30},
        ]
        metrics = [{'field': 'val', 'agg': 'stddev', 'alias': 'sd'}]
        result = self.handler.compute_aggregations(events, 3600, [], metrics)
        assert result[0]['sd'] == pytest.approx(10.0, abs=0.1)

    def test_compute_aggregations_group_by(self):
        events = [
            {'timestamp': 1700000000000, 'payload': json.dumps({'action': 'buy', 'amount': 10})},
            {'timestamp': 1700000001000, 'payload': json.dumps({'action': 'buy', 'amount': 20})},
            {'timestamp': 1700000002000, 'payload': json.dumps({'action': 'sell', 'amount': 5})},
        ]
        metrics = [{'field': 'amount', 'agg': 'sum', 'alias': 'total'}]
        result = self.handler.compute_aggregations(events, 3600, ['action'], metrics)
        groups = {r['group']: r for r in result}
        assert 'buy' in groups
        assert 'sell' in groups

    def test_compute_default_aggregations(self):
        events = [
            {'timestamp': 1000, 'payload': json.dumps({'amount': 10, 'count': 2})},
            {'timestamp': 2000, 'payload': json.dumps({'amount': 20, 'count': 3})},
        ]
        result = self.handler.compute_default_aggregations(events)
        assert len(result) == 1
        assert result[0]['count'] == 2
        assert result[0]['amount_sum'] == 30.0

    def test_compute_default_aggregations_empty(self):
        assert self.handler.compute_default_aggregations([]) == []

    def test_window_sizes(self):
        assert self.handler.WINDOW_SIZES['1m'] == 60
        assert self.handler.WINDOW_SIZES['1h'] == 3600
        assert self.handler.WINDOW_SIZES['1d'] == 86400


# ---------------------------------------------------------------------------
# Webhook Handler tests
# ---------------------------------------------------------------------------

class TestWebhookHandler:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_kinesis = MagicMock()
        self.mock_kinesis.put_records.return_value = {'FailedRecordCount': 0}
        self.mock_dynamo = MagicMock()
        self.mock_table = MagicMock()
        self.mock_dynamo.Table.return_value = self.mock_table

        patches = [
            patch('boto3.client', return_value=self.mock_kinesis),
            patch('boto3.resource', return_value=self.mock_dynamo),
        ]
        for p in patches:
            p.start()

        import sys
        sys.path.insert(0, 'services/ingestion/webhook-handler')
        if 'handler' in sys.modules:
            del sys.modules['handler']
        import handler as webhook
        self.handler = webhook

        yield
        for p in patches:
            p.stop()

    def test_parse_github_basic(self):
        body = {
            'repository': {'full_name': 'org/repo'},
            'sender': {'login': 'user1'},
            'action': 'opened',
        }
        headers = {'X-GitHub-Event': 'pull_request', 'X-GitHub-Delivery': 'del-123'}
        events = self.handler.parse_github(body, headers)
        assert len(events) == 1
        assert events[0]['event_type'] == 'github.pull_request'
        assert events[0]['event_id'] == 'del-123'

    def test_parse_github_push_with_commits(self):
        body = {
            'repository': {'full_name': 'org/repo'},
            'sender': {'login': 'user1'},
            'commits': [
                {'id': 'abc', 'author': {'name': 'dev'}, 'message': 'fix', 'added': ['a.py'], 'modified': [], 'removed': []},
                {'id': 'def', 'author': {'name': 'dev'}, 'message': 'feat', 'added': [], 'modified': ['b.py'], 'removed': []},
            ],
        }
        headers = {'X-GitHub-Event': 'push'}
        events = self.handler.parse_github(body, headers)
        assert len(events) == 3

    def test_parse_stripe(self):
        body = {
            'id': 'evt_stripe_1',
            'type': 'payment_intent.succeeded',
            'created': 1700000000,
            'data': {'object': {'amount': 1000}},
            'livemode': False,
        }
        events = self.handler.parse_stripe(body, {})
        assert len(events) == 1
        assert events[0]['event_type'] == 'stripe.payment_intent.succeeded'
        assert events[0]['livemode'] is False

    def test_parse_generic_dict(self):
        body = {'action': 'test', 'value': 42}
        events = self.handler.parse_generic(body, {})
        assert len(events) == 1
        assert events[0]['value'] == 42

    def test_parse_generic_list(self):
        body = [{'a': 1}, {'b': 2}]
        events = self.handler.parse_generic(body, {})
        assert len(events) == 2

    def test_webhook_pipeline_not_found(self):
        self.mock_table.get_item.return_value = {'Item': None}
        result = self.handler.lambda_handler({
            'pathParameters': {'pipeline_id': 'missing'},
            'headers': {},
            'body': '{}',
        }, None)
        assert result['statusCode'] == 404

    def test_webhook_success(self):
        self.mock_table.get_item.return_value = {
            'Item': {'pipeline_id': 'p1', 'source': {'webhook_type': 'generic'}},
        }
        result = self.handler.lambda_handler({
            'pathParameters': {'pipeline_id': 'p1'},
            'headers': {},
            'body': json.dumps({'action': 'test'}),
        }, None)
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['status'] == 'accepted'

    def test_webhook_invalid_json(self):
        self.mock_table.get_item.return_value = {
            'Item': {'pipeline_id': 'p1', 'source': {'webhook_type': 'generic'}},
        }
        result = self.handler.lambda_handler({
            'pathParameters': {'pipeline_id': 'p1'},
            'headers': {},
            'body': 'not-json!!!',
        }, None)
        assert result['statusCode'] == 400


# ---------------------------------------------------------------------------
# Query Runner tests
# ---------------------------------------------------------------------------

class TestQueryRunner:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_athena = MagicMock()
        self.mock_s3 = MagicMock()
        self.mock_dynamo = MagicMock()
        self.mock_pipeline_table = MagicMock()
        self.mock_run_table = MagicMock()

        def table_factory(name):
            if 'pipelines' in name:
                return self.mock_pipeline_table
            return self.mock_run_table

        self.mock_dynamo.Table.side_effect = table_factory

        patches = [
            patch('boto3.client', side_effect=lambda svc, **kw: {
                'athena': self.mock_athena, 's3': self.mock_s3,
            }.get(svc, MagicMock())),
            patch('boto3.resource', return_value=self.mock_dynamo),
        ]
        for p in patches:
            p.start()

        import sys
        sys.path.insert(0, 'services/analytics/query-runner')
        if 'handler' in sys.modules:
            del sys.modules['handler']
        import handler as query_runner
        self.handler = query_runner

        yield
        for p in patches:
            p.stop()

    def _event(self, method='GET', path='/', body=None, query_params=None, path_params=None):
        return {
            'httpMethod': method,
            'path': path,
            'body': json.dumps(body) if body else None,
            'queryStringParameters': query_params,
            'pathParameters': path_params,
        }

    def test_run_query_select(self):
        self.mock_athena.start_query_execution.return_value = {'QueryExecutionId': 'q-123'}
        result = self.handler.lambda_handler(
            self._event('POST', '/v1/query', {'sql': 'SELECT * FROM raw_events LIMIT 10'}),
            None
        )
        assert result['statusCode'] == 202
        body = json.loads(result['body'])
        assert body['query_id'] == 'q-123'

    def test_run_query_rejects_drop(self):
        result = self.handler.lambda_handler(
            self._event('POST', '/v1/query', {'sql': 'DROP TABLE raw_events'}),
            None
        )
        assert result['statusCode'] == 400

    def test_run_query_rejects_delete(self):
        result = self.handler.lambda_handler(
            self._event('POST', '/v1/query', {'sql': "SELECT * FROM t; DELETE FROM t"}),
            None
        )
        assert result['statusCode'] == 400

    def test_run_query_rejects_insert(self):
        result = self.handler.lambda_handler(
            self._event('POST', '/v1/query', {'sql': 'INSERT INTO t VALUES (1)'}),
            None
        )
        assert result['statusCode'] == 400

    def test_run_query_allows_with(self):
        self.mock_athena.start_query_execution.return_value = {'QueryExecutionId': 'q-456'}
        result = self.handler.lambda_handler(
            self._event('POST', '/v1/query', {'sql': 'WITH cte AS (SELECT 1) SELECT * FROM cte'}),
            None
        )
        assert result['statusCode'] == 202

    def test_run_query_empty_sql(self):
        result = self.handler.lambda_handler(
            self._event('POST', '/v1/query', {'sql': ''}),
            None
        )
        assert result['statusCode'] == 400

    def test_run_query_null_body(self):
        event = self._event('POST', '/v1/query')
        event['body'] = None
        result = self.handler.lambda_handler(event, None)
        assert result['statusCode'] == 400

    def test_get_stats(self):
        self.mock_run_table.scan.return_value = {
            'Items': [
                {'pipeline_id': 'p1', 'status': 'COMPLETED', 'events_count': 100, 'anomaly_count': 5, 'started_at': 1000},
                {'pipeline_id': 'p1', 'status': 'FAILED', 'events_count': 50, 'anomaly_count': 0, 'started_at': 2000},
            ],
        }
        self.mock_pipeline_table.scan.return_value = {
            'Items': [{'pipeline_id': 'p1'}, {'pipeline_id': 'p2'}],
        }
        result = self.handler.lambda_handler(
            self._event('GET', '/v1/stats'), None
        )
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['total_events'] == 150
        assert body['total_anomalies'] == 5
        assert body['completed_runs'] == 1
        assert body['failed_runs'] == 1
        assert body['active_pipelines'] == 2

    def test_not_found_route(self):
        result = self.handler.lambda_handler(
            self._event('GET', '/v1/unknown'), None
        )
        assert result['statusCode'] == 404


# ---------------------------------------------------------------------------
# Stream Processor tests
# ---------------------------------------------------------------------------

class TestStreamProcessor:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_sfn = MagicMock()
        self.mock_sfn.start_execution.return_value = {'executionArn': 'arn:test'}
        self.mock_s3 = MagicMock()
        self.mock_dynamo = MagicMock()
        self.mock_pipeline_table = MagicMock()
        self.mock_run_table = MagicMock()

        def table_factory(name):
            if 'pipelines' in name:
                return self.mock_pipeline_table
            return self.mock_run_table

        self.mock_dynamo.Table.side_effect = table_factory

        patches = [
            patch('boto3.client', side_effect=lambda svc, **kw: {
                'stepfunctions': self.mock_sfn, 's3': self.mock_s3,
            }.get(svc, MagicMock())),
            patch('boto3.resource', return_value=self.mock_dynamo),
        ]
        for p in patches:
            p.start()

        import sys
        import base64
        sys.path.insert(0, 'services/processing/stream-processor')
        if 'handler' in sys.modules:
            del sys.modules['handler']
        import handler as stream_proc
        self.handler = stream_proc
        self.base64 = base64

        yield
        for p in patches:
            p.stop()

    def _kinesis_event(self, events_by_pipeline):
        records = []
        for pipeline_id, events in events_by_pipeline.items():
            for evt in events:
                evt['pipeline_id'] = pipeline_id
                data = self.base64.b64encode(json.dumps(evt).encode()).decode()
                records.append({'kinesis': {'data': data}})
        return {'Records': records}

    def test_no_records(self):
        result = self.handler.lambda_handler({'Records': []}, None)
        assert result['status'] == 'no_records'

    def test_processes_single_pipeline(self):
        self.mock_pipeline_table.get_item.return_value = {
            'Item': {'pipeline_id': 'p1', 'steps': [], 'detect_anomalies': True, 'aggregate': True}
        }
        event = self._kinesis_event({
            'p1': [{'event_id': 'e1', 'run_id': 'r1'}, {'event_id': 'e2', 'run_id': 'r1'}],
        })
        result = self.handler.lambda_handler(event, None)
        assert result['status'] == 'processed'
        assert result['total_events'] == 2
        assert result['executions_started'] == 1

    def test_processes_multiple_pipelines(self):
        self.mock_pipeline_table.get_item.return_value = {'Item': {'pipeline_id': 'x', 'steps': []}}
        event = self._kinesis_event({
            'p1': [{'event_id': 'e1', 'run_id': 'r1'}],
            'p2': [{'event_id': 'e2', 'run_id': 'r2'}],
        })
        result = self.handler.lambda_handler(event, None)
        assert result['pipelines'] == 2
        assert result['executions_started'] == 2

    def test_skips_malformed_records(self):
        records = [
            {'kinesis': {'data': self.base64.b64encode(b'not-json').decode()}},
            {'kinesis': {'data': self.base64.b64encode(json.dumps({'pipeline_id': 'p1', 'run_id': 'r1'}).encode()).decode()}},
        ]
        self.mock_pipeline_table.get_item.return_value = {'Item': {'pipeline_id': 'p1', 'steps': []}}
        result = self.handler.lambda_handler({'Records': records}, None)
        assert result['total_events'] == 1
