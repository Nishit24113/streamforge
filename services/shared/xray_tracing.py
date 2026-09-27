"""
AWS X-Ray distributed tracing for StreamForge pipelines.

Enables end-to-end request tracking across:
- API Gateway → Lambda → Kinesis → Step Functions → S3
- Latency breakdown by service
- Error correlation across distributed components
- Service map visualization
"""

import json
import os
import time
from functools import wraps
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all


# Patch AWS SDK clients for automatic tracing
patch_all()


def trace_lambda_handler(handler):
    """
    Decorator to add X-Ray tracing to Lambda handlers.

    Usage:
        @trace_lambda_handler
        def lambda_handler(event, context):
            return {'statusCode': 200}
    """
    @wraps(handler)
    def wrapped_handler(event, context):
        # Extract trace ID from event if present
        trace_id = extract_trace_id(event)

        if trace_id:
            xray_recorder.put_annotation('trace_id', trace_id)

        # Add Lambda context metadata
        xray_recorder.put_annotation('function_name', context.function_name)
        xray_recorder.put_annotation('request_id', context.request_id)

        # Add event metadata (without sensitive data)
        add_event_metadata(event)

        try:
            result = handler(event, context)

            # Add result metadata
            if isinstance(result, dict) and 'statusCode' in result:
                xray_recorder.put_annotation('status_code', result['statusCode'])

            return result

        except Exception as e:
            # Record exception in X-Ray
            xray_recorder.put_annotation('error', str(e))
            xray_recorder.put_annotation('error_type', type(e).__name__)
            raise

    return wrapped_handler


def trace_pipeline_stage(stage_name):
    """
    Decorator to trace individual pipeline stages.

    Usage:
        @trace_pipeline_stage('transform')
        def transform_events(events):
            return transformed
    """
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            with xray_recorder.in_subsegment(stage_name) as subsegment:
                # Record input size
                if args and isinstance(args[0], list):
                    subsegment.put_metadata('input_count', len(args[0]))

                start_time = time.time()
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                # Record output size and duration
                if isinstance(result, list):
                    subsegment.put_metadata('output_count', len(result))
                subsegment.put_metadata('duration_ms', int(duration * 1000))

                return result

        return wrapped

    return decorator


def trace_s3_operation(operation_name, bucket, key):
    """
    Trace S3 operations with metadata.

    Usage:
        with trace_s3_operation('put_object', 'my-bucket', 'path/file.json'):
            s3.put_object(Bucket=bucket, Key=key, Body=data)
    """
    return xray_recorder.in_subsegment(f's3.{operation_name}',
        namespace='aws',
        meta_processor=lambda subsegment: (
            subsegment.put_annotation('bucket', bucket),
            subsegment.put_annotation('key', key)
        )
    )


def trace_dynamodb_operation(operation_name, table_name, key=None):
    """
    Trace DynamoDB operations with metadata.

    Usage:
        with trace_dynamodb_operation('get_item', 'pipelines', 'pipeline-123'):
            result = table.get_item(Key={'id': 'pipeline-123'})
    """
    return xray_recorder.in_subsegment(f'dynamodb.{operation_name}',
        namespace='aws',
        meta_processor=lambda subsegment: (
            subsegment.put_annotation('table', table_name),
            subsegment.put_annotation('key', key) if key else None
        )
    )


def trace_kinesis_operation(operation_name, stream_name, record_count=None):
    """
    Trace Kinesis operations with metadata.

    Usage:
        with trace_kinesis_operation('put_records', 'streamforge-events', 100):
            kinesis.put_records(StreamName=stream, Records=records)
    """
    return xray_recorder.in_subsegment(f'kinesis.{operation_name}',
        namespace='aws',
        meta_processor=lambda subsegment: (
            subsegment.put_annotation('stream', stream_name),
            subsegment.put_annotation('record_count', record_count) if record_count else None
        )
    )


def propagate_trace_id(pipeline_id, run_id):
    """
    Generate and propagate trace ID through pipeline.

    Returns:
        str: Trace ID to pass through pipeline stages
    """
    trace_id = f'{pipeline_id}:{run_id}:{int(time.time())}'
    xray_recorder.put_annotation('pipeline_trace_id', trace_id)
    xray_recorder.put_metadata('pipeline', {
        'pipeline_id': pipeline_id,
        'run_id': run_id,
        'timestamp': int(time.time())
    })
    return trace_id


def extract_trace_id(event):
    """
    Extract trace ID from event (API Gateway, Kinesis, Step Functions).

    Returns:
        str: Trace ID or None
    """
    # From API Gateway headers
    if 'headers' in event:
        headers = event['headers'] or {}
        trace_id = headers.get('X-Trace-Id') or headers.get('x-trace-id')
        if trace_id:
            return trace_id

    # From Kinesis records
    if 'Records' in event:
        for record in event['Records']:
            if 'kinesis' in record and 'data' in record['kinesis']:
                try:
                    data = json.loads(record['kinesis']['data'])
                    if 'trace_id' in data:
                        return data['trace_id']
                except (json.JSONDecodeError, KeyError):
                    pass

    # From Step Functions input
    if 'trace_id' in event:
        return event['trace_id']

    return None


def add_event_metadata(event):
    """Add safe event metadata to X-Ray trace."""
    # Add HTTP method and path for API Gateway
    if 'httpMethod' in event:
        xray_recorder.put_annotation('http_method', event['httpMethod'])
        if 'path' in event:
            xray_recorder.put_annotation('http_path', event['path'])

    # Add pipeline ID if present
    if 'pipeline_id' in event:
        xray_recorder.put_annotation('pipeline_id', event['pipeline_id'])

    # Add run ID if present
    if 'run_id' in event:
        xray_recorder.put_annotation('run_id', event['run_id'])

    # Add event count for batch operations
    if 'events' in event and isinstance(event['events'], list):
        xray_recorder.put_annotation('event_count', len(event['events']))


def record_pipeline_metrics(pipeline_id, run_id, metrics):
    """
    Record pipeline execution metrics in X-Ray.

    Args:
        pipeline_id: Pipeline identifier
        run_id: Run identifier
        metrics: dict with keys like 'events_processed', 'anomalies_detected', 'duration_ms'
    """
    with xray_recorder.in_subsegment('pipeline_metrics') as subsegment:
        subsegment.put_annotation('pipeline_id', pipeline_id)
        subsegment.put_annotation('run_id', run_id)

        for key, value in metrics.items():
            if isinstance(value, (int, float, bool, str)):
                subsegment.put_metadata(key, value)


def create_service_map_annotation(service_name, downstream_services):
    """
    Add annotations to help X-Ray build service map.

    Args:
        service_name: Current service name
        downstream_services: List of services this service calls
    """
    xray_recorder.put_annotation('service', service_name)
    xray_recorder.put_metadata('downstream_services', downstream_services)


# Example usage in Lambda handlers

def example_api_handler(event, context):
    """Example API handler with X-Ray tracing."""
    @trace_lambda_handler
    def handler(event, context):
        # Propagate trace ID
        trace_id = propagate_trace_id('ecommerce', 'run-123')

        # Trace Kinesis operation
        with trace_kinesis_operation('put_records', 'streamforge-events', 10):
            # kinesis.put_records(...)
            pass

        # Record metrics
        record_pipeline_metrics('ecommerce', 'run-123', {
            'events_ingested': 10,
            'duration_ms': 150
        })

        return {'statusCode': 200, 'trace_id': trace_id}

    return handler(event, context)


def example_transform_handler(event, context):
    """Example transformer with stage tracing."""
    @trace_lambda_handler
    def handler(event, context):
        events = event.get('events', [])

        @trace_pipeline_stage('validate')
        def validate(events):
            # Validation logic
            return [e for e in events if e.get('valid')]

        @trace_pipeline_stage('transform')
        def transform(events):
            # Transform logic
            return [{'transformed': e} for e in events]

        @trace_pipeline_stage('write_s3')
        def write_s3(events):
            with trace_s3_operation('put_object', 'my-bucket', 'data.json'):
                # s3.put_object(...)
                pass
            return len(events)

        validated = validate(events)
        transformed = transform(validated)
        count = write_s3(transformed)

        return {'events_processed': count}

    return handler(event, context)


# CloudWatch Insights query helpers

XRAY_INSIGHTS_QUERIES = {
    'avg_latency_by_pipeline': """
        SELECT
            annotation.pipeline_id,
            AVG(response_time) as avg_latency_ms,
            COUNT(*) as request_count
        FROM TraceSummary
        WHERE annotation.service = 'streamforge'
        GROUP BY annotation.pipeline_id
        ORDER BY avg_latency_ms DESC
    """,

    'error_rate_by_service': """
        SELECT
            service.name,
            SUM(error) / COUNT(*) * 100 as error_rate,
            SUM(error) as error_count,
            COUNT(*) as total_requests
        FROM ServiceMetrics
        WHERE timestamp > @start
        GROUP BY service.name
        ORDER BY error_rate DESC
    """,

    'p95_latency': """
        SELECT
            annotation.pipeline_id,
            PERCENTILE(response_time, 95) as p95_latency_ms,
            PERCENTILE(response_time, 99) as p99_latency_ms
        FROM TraceSummary
        WHERE annotation.service = 'streamforge'
        GROUP BY annotation.pipeline_id
    """,

    'service_dependency_graph': """
        SELECT
            service.name as from_service,
            edge.end.name as to_service,
            COUNT(*) as call_count,
            AVG(edge.response_time) as avg_latency_ms
        FROM ServiceGraph
        WHERE timestamp > @start
        GROUP BY service.name, edge.end.name
    """
}
