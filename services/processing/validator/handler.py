import json
import os
import time
import boto3

DATA_LAKE_BUCKET = os.environ.get('DATA_LAKE_BUCKET', 'streamforge-lake')
RUN_HISTORY_TABLE = os.environ.get('RUN_HISTORY_TABLE', 'streamforge-runs')

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
run_table = dynamodb.Table(RUN_HISTORY_TABLE)

TYPE_VALIDATORS = {
    'string': lambda v: isinstance(v, str),
    'number': lambda v: isinstance(v, (int, float)),
    'integer': lambda v: isinstance(v, int),
    'boolean': lambda v: isinstance(v, bool),
    'array': lambda v: isinstance(v, list),
    'object': lambda v: isinstance(v, dict),
}


def lambda_handler(event, context):
    pipeline_id = event['pipeline_id']
    run_id = event['run_id']
    raw_location = event['raw_location']
    pipeline_config = event.get('pipeline_config', {})

    events = load_events(raw_location)

    validation_steps = [
        step for step in pipeline_config.get('steps', [])
        if step.get('type') == 'validate'
    ]

    valid_events = []
    rejected_events = []

    for evt in events:
        payload = evt if isinstance(evt, dict) else json.loads(evt.get('payload', '{}'))
        is_valid = True
        rejection_reasons = []

        for step in validation_steps:
            schema = step.get('schema', {})
            for field, expected_type in schema.items():
                if field not in payload:
                    if step.get('required', True):
                        is_valid = False
                        rejection_reasons.append(f'Missing required field: {field}')
                elif expected_type in TYPE_VALIDATORS:
                    if not TYPE_VALIDATORS[expected_type](payload[field]):
                        is_valid = False
                        rejection_reasons.append(
                            f'Field {field}: expected {expected_type}, '
                            f'got {type(payload[field]).__name__}'
                        )

            null_check = step.get('reject_nulls', [])
            for field in null_check:
                if field in payload and payload[field] is None:
                    is_valid = False
                    rejection_reasons.append(f'Null value in non-nullable field: {field}')

            range_checks = step.get('range_checks', {})
            for field, bounds in range_checks.items():
                if field in payload:
                    val = payload[field]
                    if isinstance(val, (int, float)):
                        if 'min' in bounds and val < bounds['min']:
                            is_valid = False
                            rejection_reasons.append(f'{field} below minimum: {val} < {bounds["min"]}')
                        if 'max' in bounds and val > bounds['max']:
                            is_valid = False
                            rejection_reasons.append(f'{field} above maximum: {val} > {bounds["max"]}')

        if is_valid:
            valid_events.append(evt)
        else:
            evt['_rejection_reasons'] = rejection_reasons
            rejected_events.append(evt)

    if rejected_events:
        write_rejected(rejected_events, pipeline_id, run_id)

    update_run_status(pipeline_id, run_id, len(valid_events), len(rejected_events))

    return {
        'pipeline_id': pipeline_id,
        'run_id': run_id,
        'events_count': event.get('events_count', len(events)),
        'valid_count': len(valid_events),
        'rejected_count': len(rejected_events),
        'raw_location': raw_location,
        'pipeline_config': pipeline_config,
        'events_processed': len(valid_events),
        'anomalies_detected': 0,
    }


def load_events(raw_location):
    parts = raw_location.replace('s3://', '').split('/', 1)
    bucket = parts[0]
    key = parts[1]

    obj = s3.get_object(Bucket=bucket, Key=key)
    content = obj['Body'].read().decode('utf-8')
    data = json.loads(content)

    return data if isinstance(data, list) else [data]


def write_rejected(events, pipeline_id, run_id):
    from datetime import datetime
    now = datetime.utcnow()
    key = f'rejected/{pipeline_id}/year={now.year}/month={now.month:02d}/day={now.day:02d}/{run_id}.json'

    s3.put_object(
        Bucket=DATA_LAKE_BUCKET,
        Key=key,
        Body=json.dumps(events, default=str),
        ContentType='application/json',
    )


def update_run_status(pipeline_id, run_id, valid_count, rejected_count):
    run_table.update_item(
        Key={'pipeline_id': pipeline_id, 'run_id': run_id},
        UpdateExpression='SET #s = :s, valid_count = :v, rejected_count = :r, validated_at = :t',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={
            ':s': 'VALIDATED',
            ':v': valid_count,
            ':r': rejected_count,
            ':t': int(time.time()),
        },
    )
