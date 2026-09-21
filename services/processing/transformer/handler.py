import json
import os
import time
import uuid
import copy
import boto3

DATA_LAKE_BUCKET = os.environ.get('DATA_LAKE_BUCKET', 'streamforge-lake')
RUN_HISTORY_TABLE = os.environ.get('RUN_HISTORY_TABLE', 'streamforge-runs')

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
run_table = dynamodb.Table(RUN_HISTORY_TABLE)

def _get_operations():
    return {
        'rename': op_rename,
        'add_field': op_add_field,
        'remove_field': op_remove_field,
        'cast': op_cast,
        'flatten': op_flatten,
        'filter': op_filter,
        'map_values': op_map_values,
        'extract': op_extract,
        'lowercase': op_lowercase,
        'uppercase': op_uppercase,
        'default': op_default,
        'hash': op_hash,
    }


def lambda_handler(event, context):
    pipeline_id = event['pipeline_id']
    run_id = event['run_id']
    raw_location = event['raw_location']
    pipeline_config = event.get('pipeline_config', {})

    events = load_events(raw_location)

    transform_steps = [
        step for step in pipeline_config.get('steps', [])
        if step.get('type') == 'transform'
    ]

    transformed = []
    now = int(time.time() * 1000)

    for evt in events:
        payload = evt.get('payload', '{}')
        if isinstance(payload, str):
            try:
                record = json.loads(payload)
            except json.JSONDecodeError:
                record = {'raw': payload}
        else:
            record = copy.deepcopy(payload)

        ops = _get_operations()
        for step in transform_steps:
            operations = step.get('operations', [])
            for op_config in operations:
                op_name = op_config.get('op', '')
                handler = ops.get(op_name)
                if handler:
                    record = handler(record, op_config)
                    if record is None:
                        break
            if record is None:
                break

        if record is None:
            continue

        clean_event = {
            'event_id': evt.get('event_id', f'evt-{uuid.uuid4().hex[:12]}'),
            'pipeline_id': pipeline_id,
            'timestamp': evt.get('timestamp', now),
            'source': evt.get('source', 'unknown'),
            'event_type': evt.get('event_type', 'unknown'),
            'payload': json.dumps(record, default=str),
            'processed_at': now,
            'is_anomaly': False,
            'anomaly_score': 0.0,
        }
        transformed.append(clean_event)

    clean_location = write_clean_events(transformed, pipeline_id, run_id)

    update_run_status(pipeline_id, run_id, len(transformed))

    return {
        'pipeline_id': pipeline_id,
        'run_id': run_id,
        'events_count': event.get('events_count', len(events)),
        'events_processed': len(transformed),
        'clean_location': clean_location,
        'raw_location': raw_location,
        'pipeline_config': pipeline_config,
        'anomalies_detected': 0,
    }


def op_rename(record, config):
    from_field = config.get('from', '')
    to_field = config.get('to', '')
    if from_field in record:
        record[to_field] = record.pop(from_field)
    return record


def op_add_field(record, config):
    name = config.get('name', '')
    value = config.get('value', '')
    if value == '$NOW':
        value = int(time.time() * 1000)
    elif value == '$UUID':
        value = str(uuid.uuid4())
    elif value == '$DATE':
        from datetime import datetime
        value = datetime.utcnow().isoformat()
    record[name] = value
    return record


def op_remove_field(record, config):
    field = config.get('field', '')
    record.pop(field, None)
    return record


def op_cast(record, config):
    field = config.get('field', '')
    target_type = config.get('to', 'string')
    if field in record:
        try:
            if target_type in ('int', 'integer'):
                record[field] = int(float(record[field]))
            elif target_type in ('float', 'decimal', 'number'):
                record[field] = float(record[field])
            elif target_type == 'string':
                record[field] = str(record[field])
            elif target_type == 'boolean':
                record[field] = bool(record[field])
        except (ValueError, TypeError):
            pass
    return record


def op_flatten(record, config):
    prefix = config.get('prefix', '')
    field = config.get('field', '')
    if field in record and isinstance(record[field], dict):
        nested = record.pop(field)
        for k, v in nested.items():
            key = f'{prefix}{k}' if prefix else k
            record[key] = v
    return record


def op_filter(record, config):
    field = config.get('field', '')
    operator = config.get('operator', 'eq')
    value = config.get('value')

    if field not in record:
        return record

    actual = record[field]
    if operator == 'eq' and actual != value:
        return None
    if operator == 'neq' and actual == value:
        return None
    if operator == 'gt' and not (isinstance(actual, (int, float)) and actual > value):
        return None
    if operator == 'lt' and not (isinstance(actual, (int, float)) and actual < value):
        return None
    if operator == 'contains' and value not in str(actual):
        return None

    return record


def op_map_values(record, config):
    field = config.get('field', '')
    mapping = config.get('mapping', {})
    if field in record and str(record[field]) in mapping:
        record[field] = mapping[str(record[field])]
    return record


def op_extract(record, config):
    source = config.get('source', '')
    target = config.get('target', '')
    pattern = config.get('key', '')
    if source in record and isinstance(record[source], dict):
        record[target] = record[source].get(pattern, None)
    return record


def op_lowercase(record, config):
    field = config.get('field', '')
    if field in record and isinstance(record[field], str):
        record[field] = record[field].lower()
    return record


def op_uppercase(record, config):
    field = config.get('field', '')
    if field in record and isinstance(record[field], str):
        record[field] = record[field].upper()
    return record


def op_default(record, config):
    field = config.get('field', '')
    value = config.get('value')
    if field not in record or record[field] is None:
        record[field] = value
    return record


def op_hash(record, config):
    import hashlib
    field = config.get('field', '')
    algorithm = config.get('algorithm', 'sha256')
    if field in record:
        hasher = hashlib.new(algorithm)
        hasher.update(str(record[field]).encode('utf-8'))
        record[field] = hasher.hexdigest()
    return record


def load_events(raw_location):
    parts = raw_location.replace('s3://', '').split('/', 1)
    obj = s3.get_object(Bucket=parts[0], Key=parts[1])
    content = obj['Body'].read().decode('utf-8')
    data = json.loads(content)
    return data if isinstance(data, list) else [data]


def write_clean_events(events, pipeline_id, run_id):
    from datetime import datetime
    now = datetime.utcnow()
    key = f'clean/{pipeline_id}/year={now.year}/month={now.month:02d}/day={now.day:02d}/{run_id}.json'

    s3.put_object(
        Bucket=DATA_LAKE_BUCKET,
        Key=key,
        Body=json.dumps(events, default=str),
        ContentType='application/json',
    )
    return f's3://{DATA_LAKE_BUCKET}/{key}'


def update_run_status(pipeline_id, run_id, transformed_count):
    run_table.update_item(
        Key={'pipeline_id': pipeline_id, 'run_id': run_id},
        UpdateExpression='SET #s = :s, transformed_count = :tc, transformed_at = :t',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={
            ':s': 'TRANSFORMED',
            ':tc': transformed_count,
            ':t': int(time.time()),
        },
    )
