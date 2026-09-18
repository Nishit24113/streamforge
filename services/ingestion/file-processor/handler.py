import json
import os
import csv
import io
import time
import uuid
import boto3

KINESIS_STREAM = os.environ.get('KINESIS_STREAM', 'streamforge-events')
PIPELINE_TABLE = os.environ.get('PIPELINE_TABLE', 'streamforge-pipelines')
DATA_LAKE_BUCKET = os.environ.get('DATA_LAKE_BUCKET', 'streamforge-lake')

kinesis = boto3.client('kinesis')
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
pipeline_table = dynamodb.Table(PIPELINE_TABLE)


def lambda_handler(event, context):
    for record in event.get('Records', []):
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']

        if not key.startswith('uploads/'):
            continue

        parts = key.split('/')
        pipeline_id = parts[1] if len(parts) > 1 else 'default'

        try:
            process_file(bucket, key, pipeline_id)
        except Exception as e:
            print(f'Error processing {key}: {e}')
            raise

    return {'status': 'processed', 'files': len(event.get('Records', []))}


def process_file(bucket, key, pipeline_id):
    obj = s3.get_object(Bucket=bucket, Key=key)
    content = obj['Body'].read()
    content_type = obj.get('ContentType', '')

    if key.endswith('.csv') or 'csv' in content_type:
        events = parse_csv(content.decode('utf-8'))
    elif key.endswith('.json') or 'json' in content_type:
        events = parse_json(content.decode('utf-8'))
    else:
        events = parse_json(content.decode('utf-8'))

    now = int(time.time() * 1000)
    run_id = f'file-{uuid.uuid4().hex[:12]}'

    records = []
    for evt in events:
        record = {
            'event_id': evt.get('event_id', f'evt-{uuid.uuid4().hex[:12]}'),
            'pipeline_id': pipeline_id,
            'timestamp': evt.get('timestamp', now),
            'source': f'file:{key.split(".")[-1]}',
            'event_type': evt.get('event_type', evt.get('type', 'file_upload')),
            'payload': json.dumps(evt),
            'ingested_at': now,
            'run_id': run_id,
        }
        records.append({
            'Data': json.dumps(record).encode('utf-8'),
            'PartitionKey': pipeline_id,
        })

    for i in range(0, len(records), 100):
        batch = records[i:i + 100]
        kinesis.put_records(
            StreamName=KINESIS_STREAM,
            Records=batch,
        )

    print(f'Processed {len(records)} events from {key}')
    return len(records)


def parse_csv(content):
    reader = csv.DictReader(io.StringIO(content))
    events = []
    for row in reader:
        event = dict(row)
        if 'timestamp' in event:
            try:
                event['timestamp'] = int(float(event['timestamp']))
            except (ValueError, TypeError):
                event['timestamp'] = int(time.time() * 1000)
        events.append(event)
    return events


def parse_json(content):
    data = json.loads(content)
    if isinstance(data, list):
        return data
    if 'events' in data:
        return data['events']
    if 'data' in data:
        return data['data'] if isinstance(data['data'], list) else [data['data']]
    return [data]
