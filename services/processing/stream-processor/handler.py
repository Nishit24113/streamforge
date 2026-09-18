import json
import os
import time
import uuid
import base64
import boto3
from collections import defaultdict

STATE_MACHINE_ARN = os.environ.get('STATE_MACHINE_ARN', '')
PIPELINE_TABLE = os.environ.get('PIPELINE_TABLE', 'streamforge-pipelines')
RUN_HISTORY_TABLE = os.environ.get('RUN_HISTORY_TABLE', 'streamforge-runs')
DATA_LAKE_BUCKET = os.environ.get('DATA_LAKE_BUCKET', 'streamforge-lake')

sfn = boto3.client('stepfunctions')
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

pipeline_table = dynamodb.Table(PIPELINE_TABLE)
run_table = dynamodb.Table(RUN_HISTORY_TABLE)


def lambda_handler(event, context):
    records = event.get('Records', [])
    if not records:
        return {'status': 'no_records'}

    events_by_pipeline = defaultdict(list)

    for record in records:
        try:
            data = base64.b64decode(record['kinesis']['data'])
            event_data = json.loads(data)
            pipeline_id = event_data.get('pipeline_id', 'default')
            events_by_pipeline[pipeline_id].append(event_data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f'Error decoding record: {e}')
            continue

    executions_started = 0

    for pipeline_id, events in events_by_pipeline.items():
        pipeline_config = get_pipeline_config(pipeline_id)

        run_id = events[0].get('run_id', f'stream-{uuid.uuid4().hex[:12]}')

        raw_key = write_raw_events(events, pipeline_id, run_id)

        run_table.put_item(Item={
            'pipeline_id': pipeline_id,
            'run_id': run_id,
            'status': 'PROCESSING',
            'started_at': int(time.time()),
            'events_count': len(events),
            'raw_location': raw_key,
            'ttl': int(time.time()) + (30 * 24 * 60 * 60),
        })

        if STATE_MACHINE_ARN:
            sfn.start_execution(
                stateMachineArn=STATE_MACHINE_ARN,
                name=f'{pipeline_id}-{run_id}',
                input=json.dumps({
                    'pipeline_id': pipeline_id,
                    'run_id': run_id,
                    'events_count': len(events),
                    'raw_location': raw_key,
                    'pipeline_config': pipeline_config,
                }),
            )
            executions_started += 1

    return {
        'status': 'processed',
        'pipelines': len(events_by_pipeline),
        'total_events': sum(len(e) for e in events_by_pipeline.values()),
        'executions_started': executions_started,
    }


def get_pipeline_config(pipeline_id):
    try:
        result = pipeline_table.get_item(Key={'pipeline_id': pipeline_id})
        item = result.get('Item', {})
        return {
            'steps': item.get('steps', []),
            'detect_anomalies': item.get('detect_anomalies', False),
            'aggregate': item.get('aggregate', False),
            'output': item.get('output', {}),
        }
    except Exception:
        return {
            'steps': [],
            'detect_anomalies': True,
            'aggregate': True,
            'output': {},
        }


def write_raw_events(events, pipeline_id, run_id):
    from datetime import datetime

    now = datetime.utcnow()
    partition = f'year={now.year}/month={now.month:02d}/day={now.day:02d}'
    key = f'raw/{pipeline_id}/{partition}/{run_id}.json'

    s3.put_object(
        Bucket=DATA_LAKE_BUCKET,
        Key=key,
        Body=json.dumps(events, default=str),
        ContentType='application/json',
    )

    return f's3://{DATA_LAKE_BUCKET}/{key}'
