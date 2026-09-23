import json
import os
import time
import uuid
import boto3

KINESIS_STREAM = os.environ.get('KINESIS_STREAM', 'streamforge-events')
PIPELINE_TABLE = os.environ.get('PIPELINE_TABLE', 'streamforge-pipelines')
RUN_HISTORY_TABLE = os.environ.get('RUN_HISTORY_TABLE', 'streamforge-runs')
DATA_LAKE_BUCKET = os.environ.get('DATA_LAKE_BUCKET', 'streamforge-lake')
DLQ_URL = os.environ.get('DLQ_URL', '')

kinesis = boto3.client('kinesis')
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
sqs = boto3.client('sqs')

pipeline_table = dynamodb.Table(PIPELINE_TABLE)
run_table = dynamodb.Table(RUN_HISTORY_TABLE)


def get_org_id(event):
    headers = event.get('headers') or {}
    return headers.get('X-Org-Id') or headers.get('x-org-id') or 'default'


def lambda_handler(event, context):
    http_method = event.get('httpMethod', 'GET')
    path = event.get('path', '/')
    path_params = event.get('pathParameters') or {}
    org_id = get_org_id(event)

    try:
        if path == '/v1/health' and http_method == 'GET':
            return handle_health()

        if path == '/v1/ingest' and http_method == 'POST':
            return handle_ingest(event, org_id)

        if path == '/v1/upload' and http_method == 'POST':
            return handle_upload(event, org_id)

        # Template endpoints
        if path == '/v1/templates' and http_method == 'GET':
            return handle_list_templates()

        if '/v1/templates/' in path and http_method == 'GET':
            template_id = path_params.get('template_id', '')
            return handle_get_template(template_id)

        if path == '/v1/pipelines/from-template' and http_method == 'POST':
            return handle_create_from_template(event, org_id)

        # Pipeline endpoints
        if path == '/v1/pipelines' and http_method == 'GET':
            return handle_list_pipelines(org_id)

        if path == '/v1/pipelines' and http_method == 'POST':
            return handle_create_pipeline(event, org_id)

        if '/v1/pipelines/' in path and '/runs' in path:
            pipeline_id = path_params.get('pipeline_id', '')
            return handle_get_runs(pipeline_id)

        if '/v1/pipelines/' in path:
            pipeline_id = path_params.get('pipeline_id', '')
            return handle_get_pipeline(pipeline_id)

        return response(404, {'error': 'Not found'})

    except Exception as e:
        return response(500, {'error': str(e)})


def handle_health():
    return response(200, {
        'status': 'healthy',
        'service': 'streamforge-ingestion',
        'timestamp': int(time.time()),
        'version': '1.0.0',
    })


def handle_ingest(event, org_id='default'):
    body = json.loads(event.get('body') or '{}')
    pipeline_id = body.get('pipeline', 'default')
    events = body.get('events', [])

    if not events:
        return response(400, {'error': 'No events provided'})

    if len(events) > 500:
        return response(400, {'error': 'Maximum 500 events per request'})

    run_id = f'run-{uuid.uuid4().hex[:12]}'
    now = int(time.time() * 1000)

    records = []
    for evt in events:
        record = {
            'event_id': evt.get('event_id', f'evt-{uuid.uuid4().hex[:12]}'),
            'pipeline_id': pipeline_id,
            'timestamp': evt.get('timestamp', now),
            'source': evt.get('source', 'api'),
            'event_type': evt.get('event_type', evt.get('type', 'unknown')),
            'org_id': org_id,
            'payload': json.dumps(evt),
            'ingested_at': now,
            'run_id': run_id,
        }

        records.append({
            'Data': json.dumps(record).encode('utf-8'),
            'PartitionKey': pipeline_id,
        })

    failed = 0
    for i in range(0, len(records), 100):
        batch = records[i:i + 100]
        try:
            resp = kinesis.put_records(
                StreamName=KINESIS_STREAM,
                Records=batch,
            )
            failed += resp.get('FailedRecordCount', 0)
        except Exception as e:
            if DLQ_URL:
                for rec in batch:
                    sqs.send_message(
                        QueueUrl=DLQ_URL,
                        MessageBody=rec['Data'].decode('utf-8'),
                    )
            failed += len(batch)

    run_table.put_item(Item={
        'pipeline_id': pipeline_id,
        'run_id': run_id,
        'status': 'INGESTED',
        'started_at': int(time.time()),
        'events_count': len(events),
        'failed_count': failed,
        'ttl': int(time.time()) + (30 * 24 * 60 * 60),
    })

    return response(202, {
        'status': 'accepted',
        'pipeline': pipeline_id,
        'run_id': run_id,
        'events_received': len(events),
        'events_failed': failed,
    })


def handle_upload(event, org_id='default'):
    body = json.loads(event.get('body') or '{}')
    pipeline_id = body.get('pipeline', 'default')
    filename = body.get('filename', f'upload-{uuid.uuid4().hex[:8]}.json')
    content_type = body.get('content_type', 'application/json')

    upload_key = f'uploads/{org_id}/{pipeline_id}/{int(time.time())}/{filename}'

    presigned = s3.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': DATA_LAKE_BUCKET,
            'Key': upload_key,
            'ContentType': content_type,
        },
        ExpiresIn=3600,
    )

    return response(200, {
        'upload_url': presigned,
        'key': upload_key,
        'pipeline': pipeline_id,
        'expires_in': 3600,
    })


def handle_list_pipelines(org_id='default'):
    from boto3.dynamodb.conditions import Attr
    result = pipeline_table.scan(
        Limit=100,
        FilterExpression=Attr('org_id').eq(org_id) | Attr('org_id').not_exists(),
    )
    pipelines = result.get('Items', [])

    return response(200, {
        'pipelines': pipelines,
        'count': len(pipelines),
    })


def handle_create_pipeline(event, org_id='default'):
    body = json.loads(event.get('body') or '{}')

    pipeline_id = body.get('pipeline_id', f'pipeline-{uuid.uuid4().hex[:8]}')
    name = body.get('name', pipeline_id)

    pipeline = {
        'pipeline_id': pipeline_id,
        'name': name,
        'description': body.get('description', ''),
        'steps': body.get('steps', []),
        'source': body.get('source', {'type': 'api', 'format': 'json'}),
        'output': body.get('output', {}),
        'detect_anomalies': body.get('detect_anomalies', False),
        'aggregate': body.get('aggregate', False),
        'created_at': int(time.time()),
        'updated_at': int(time.time()),
        'status': 'ACTIVE',
        'org_id': org_id,
    }

    pipeline_table.put_item(Item=pipeline)

    return response(201, {
        'status': 'created',
        'pipeline': pipeline,
    })


def handle_get_pipeline(pipeline_id):
    result = pipeline_table.get_item(Key={'pipeline_id': pipeline_id})
    item = result.get('Item')

    if not item:
        return response(404, {'error': f'Pipeline {pipeline_id} not found'})

    return response(200, {'pipeline': item})


def handle_get_runs(pipeline_id):
    result = run_table.query(
        KeyConditionExpression='pipeline_id = :pid',
        ExpressionAttributeValues={':pid': pipeline_id},
        ScanIndexForward=False,
        Limit=50,
    )

    return response(200, {
        'pipeline_id': pipeline_id,
        'runs': result.get('Items', []),
        'count': result.get('Count', 0),
    })


def handle_list_templates():
    """List all available pipeline templates."""
    templates = [
        {
            'id': 'ecommerce',
            'name': 'E-Commerce Events',
            'description': 'Track purchases, cart actions, and detect fraudulent transactions',
            'category': 'retail',
            'use_cases': ['fraud detection', 'revenue tracking', 'customer analytics']
        },
        {
            'id': 'iot-sensors',
            'name': 'IoT Sensor Data',
            'description': 'Monitor sensor readings with anomaly detection for temperature, pressure, humidity',
            'category': 'industrial',
            'use_cases': ['predictive maintenance', 'quality control', 'environmental monitoring']
        },
        {
            'id': 'web-analytics',
            'name': 'Web Analytics',
            'description': 'Track page views, user sessions, and conversions with PII hashing',
            'category': 'marketing',
            'use_cases': ['conversion tracking', 'session analysis', 'GDPR compliance']
        },
        {
            'id': 'application-logs',
            'name': 'Application Logs',
            'description': 'Aggregate error rates, track exceptions, and monitor application health',
            'category': 'observability',
            'use_cases': ['error tracking', 'performance monitoring', 'alerting']
        },
        {
            'id': 'financial-transactions',
            'name': 'Financial Transactions',
            'description': 'Monitor payments and transfers with fraud detection and compliance tracking',
            'category': 'fintech',
            'use_cases': ['fraud detection', 'compliance reporting', 'transaction analytics']
        }
    ]

    return response(200, {
        'templates': templates,
        'count': len(templates)
    })


def handle_get_template(template_id):
    """Get a specific template with full configuration and variables."""
    # In production, these would be loaded from S3 or DynamoDB
    # For now, return embedded template data
    template_map = {
        'ecommerce': {
            'id': 'ecommerce',
            'name': 'E-Commerce Events',
            'description': 'Track purchases, cart actions, and detect fraudulent transactions using anomaly detection',
            'category': 'retail',
            'variables': {
                'pipeline_name': {'description': 'Name for your pipeline', 'default': 'ecommerce-events', 'required': True},
                'anomaly_threshold': {'description': 'Contamination rate for fraud detection (0.01-0.10)', 'default': '0.05', 'required': False},
                'aggregation_window': {'description': 'Time window for revenue aggregation (1m, 5m, 15m, 1h)', 'default': '1h', 'required': False}
            },
            'sample_event': {
                'user_id': 'user_12345',
                'email': 'customer@example.com',
                'event_type': 'purchase',
                'amount': 99.99,
                'currency': 'USD',
                'product_id': 'prod_abc',
                'timestamp': 1695000000000
            }
        }
    }

    if template_id not in template_map:
        return response(404, {'error': f'Template {template_id} not found'})

    return response(200, {'template': template_map[template_id]})


def handle_create_from_template(event, org_id='default'):
    """Create a pipeline from a template with variable substitution."""
    body = json.loads(event.get('body') or '{}')

    template_id = body.get('template_id')
    variables = body.get('variables', {})

    if not template_id:
        return response(400, {'error': 'template_id required'})

    # Get the template configuration (simplified for now)
    # In production, this would load full template from S3
    config_templates = {
        'ecommerce': {
            'name': variables.get('pipeline_name', 'ecommerce-events'),
            'steps': [
                {'type': 'validate', 'schema': {'user_id': 'string', 'amount': 'number'}},
                {'type': 'transform', 'operations': [{'op': 'hash', 'field': 'email', 'algorithm': 'sha256'}]},
                {'type': 'detect_anomalies', 'field': 'amount', 'method': 'isolation_forest', 'contamination': float(variables.get('anomaly_threshold', 0.05))},
                {'type': 'aggregate', 'window': variables.get('aggregation_window', '1h'), 'metrics': [{'field': 'amount', 'agg': 'sum', 'alias': 'total_revenue'}]}
            ],
            'detect_anomalies': True,
            'aggregate': True
        },
        'iot-sensors': {
            'name': variables.get('pipeline_name', 'iot-sensor-monitoring'),
            'steps': [
                {'type': 'validate', 'schema': {'device_id': 'string', 'temperature': 'number'}},
                {'type': 'detect_anomalies', 'field': 'temperature', 'method': 'zscore', 'threshold': float(variables.get('zscore_threshold', 2.5))},
                {'type': 'aggregate', 'window': variables.get('aggregation_window', '5m'), 'metrics': [{'field': 'temperature', 'agg': 'avg', 'alias': 'avg_temp'}]}
            ],
            'detect_anomalies': True,
            'aggregate': True
        }
    }

    if template_id not in config_templates:
        return response(404, {'error': f'Template {template_id} not found'})

    config = config_templates[template_id]
    pipeline_id = config['name']

    # Create the pipeline
    pipeline = {
        'pipeline_id': pipeline_id,
        'name': config['name'],
        'description': f'Pipeline created from template: {template_id}',
        'steps': config['steps'],
        'detect_anomalies': config.get('detect_anomalies', False),
        'aggregate': config.get('aggregate', False),
        'template_id': template_id,
        'created_at': int(time.time()),
        'updated_at': int(time.time()),
        'status': 'ACTIVE',
        'org_id': org_id,
    }

    pipeline_table.put_item(Item=pipeline)

    return response(201, {
        'status': 'created',
        'pipeline_id': pipeline_id,
        'template_id': template_id,
        'pipeline': pipeline,
        'message': f'Pipeline {pipeline_id} created from template {template_id}'
    })


def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Api-Key,X-Pipeline-Id,X-Org-Id',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
        },
        'body': json.dumps(body, default=str),
    }
