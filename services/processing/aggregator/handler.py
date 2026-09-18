import json
import os
import time
import math
import boto3
from collections import defaultdict

DATA_LAKE_BUCKET = os.environ.get('DATA_LAKE_BUCKET', 'streamforge-lake')
RUN_HISTORY_TABLE = os.environ.get('RUN_HISTORY_TABLE', 'streamforge-runs')

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
run_table = dynamodb.Table(RUN_HISTORY_TABLE)

WINDOW_SIZES = {
    '1m': 60,
    '5m': 300,
    '15m': 900,
    '1h': 3600,
    '6h': 21600,
    '1d': 86400,
}


def lambda_handler(event, context):
    pipeline_id = event['pipeline_id']
    run_id = event['run_id']
    clean_location = event.get('clean_location', event.get('raw_location', ''))
    pipeline_config = event.get('pipeline_config', {})

    events = load_events(clean_location)

    agg_steps = [
        step for step in pipeline_config.get('steps', [])
        if step.get('type') == 'aggregate'
    ]

    all_aggregations = []

    for step in agg_steps:
        window = step.get('window', '1h')
        group_by = step.get('group_by', [])
        metrics = step.get('metrics', [])

        window_seconds = WINDOW_SIZES.get(window, 3600)
        aggregations = compute_aggregations(events, window_seconds, group_by, metrics)
        all_aggregations.extend(aggregations)

    if not agg_steps:
        aggregations = compute_default_aggregations(events)
        all_aggregations.extend(aggregations)

    agg_location = ''
    if all_aggregations:
        agg_location = write_aggregations(all_aggregations, pipeline_id, run_id)

    update_run_status(pipeline_id, run_id, len(all_aggregations))

    return {
        'pipeline_id': pipeline_id,
        'run_id': run_id,
        'events_count': event.get('events_count', len(events)),
        'events_processed': event.get('events_processed', len(events)),
        'anomalies_detected': event.get('anomalies_detected', 0),
        'aggregations_count': len(all_aggregations),
        'agg_location': agg_location,
    }


def compute_aggregations(events, window_seconds, group_by, metrics):
    buckets = defaultdict(list)

    for evt in events:
        ts = evt.get('timestamp', 0)
        if isinstance(ts, str):
            ts = int(float(ts))
        window_start = (ts // (window_seconds * 1000)) * (window_seconds * 1000)

        payload = evt.get('payload', '{}')
        if isinstance(payload, str):
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = {}
        else:
            data = payload

        group_key_parts = [str(data.get(g, evt.get(g, 'unknown'))) for g in group_by]
        group_key = '|'.join(group_key_parts) if group_key_parts else 'all'

        bucket_key = f'{window_start}:{group_key}'
        buckets[bucket_key].append({**data, **evt})

    results = []
    for bucket_key, bucket_events in buckets.items():
        window_start, group_key = bucket_key.split(':', 1)

        agg = {
            'window_start': int(window_start),
            'window_end': int(window_start) + window_seconds * 1000,
            'group': group_key,
            'count': len(bucket_events),
        }

        for metric in metrics:
            field = metric.get('field', '')
            agg_type = metric.get('agg', 'count')
            alias = metric.get('alias', f'{field}_{agg_type}')

            values = []
            for e in bucket_events:
                val = e.get(field)
                if isinstance(val, (int, float)):
                    values.append(float(val))
                elif isinstance(val, str):
                    try:
                        values.append(float(val))
                    except ValueError:
                        pass

            if not values and agg_type != 'count':
                agg[alias] = None
                continue

            if agg_type == 'sum':
                agg[alias] = sum(values)
            elif agg_type == 'avg':
                agg[alias] = sum(values) / len(values) if values else 0
            elif agg_type == 'min':
                agg[alias] = min(values) if values else None
            elif agg_type == 'max':
                agg[alias] = max(values) if values else None
            elif agg_type == 'count':
                agg[alias] = len(bucket_events)
            elif agg_type == 'count_distinct':
                distinct = set()
                for e in bucket_events:
                    v = e.get(field)
                    if v is not None:
                        distinct.add(str(v))
                agg[alias] = len(distinct)
            elif agg_type == 'stddev':
                if len(values) > 1:
                    mean = sum(values) / len(values)
                    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
                    agg[alias] = math.sqrt(variance)
                else:
                    agg[alias] = 0
            elif agg_type == 'p50':
                agg[alias] = percentile(values, 50)
            elif agg_type == 'p95':
                agg[alias] = percentile(values, 95)
            elif agg_type == 'p99':
                agg[alias] = percentile(values, 99)

        results.append(agg)

    return sorted(results, key=lambda x: x.get('window_start', 0))


def compute_default_aggregations(events):
    if not events:
        return []

    numeric_fields = defaultdict(list)
    for evt in events:
        payload = evt.get('payload', '{}')
        if isinstance(payload, str):
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
        else:
            data = payload

        for k, v in data.items():
            if isinstance(v, (int, float)):
                numeric_fields[k].append(float(v))

    agg = {
        'window_start': min(e.get('timestamp', 0) for e in events),
        'window_end': max(e.get('timestamp', 0) for e in events),
        'group': 'all',
        'count': len(events),
    }

    for field, values in numeric_fields.items():
        if values:
            agg[f'{field}_sum'] = sum(values)
            agg[f'{field}_avg'] = sum(values) / len(values)
            agg[f'{field}_min'] = min(values)
            agg[f'{field}_max'] = max(values)

    return [agg]


def percentile(values, pct):
    if not values:
        return 0
    sorted_vals = sorted(values)
    idx = (len(sorted_vals) - 1) * pct / 100
    lower = int(idx)
    upper = lower + 1
    if upper >= len(sorted_vals):
        return sorted_vals[-1]
    weight = idx - lower
    return sorted_vals[lower] * (1 - weight) + sorted_vals[upper] * weight


def load_events(location):
    parts = location.replace('s3://', '').split('/', 1)
    obj = s3.get_object(Bucket=parts[0], Key=parts[1])
    content = obj['Body'].read().decode('utf-8')
    data = json.loads(content)
    return data if isinstance(data, list) else [data]


def write_aggregations(aggregations, pipeline_id, run_id):
    from datetime import datetime
    now = datetime.utcnow()
    key = f'agg/{pipeline_id}/year={now.year}/month={now.month:02d}/day={now.day:02d}/{run_id}.json'

    s3.put_object(
        Bucket=DATA_LAKE_BUCKET,
        Key=key,
        Body=json.dumps(aggregations, default=str),
        ContentType='application/json',
    )
    return f's3://{DATA_LAKE_BUCKET}/{key}'


def update_run_status(pipeline_id, run_id, agg_count):
    run_table.update_item(
        Key={'pipeline_id': pipeline_id, 'run_id': run_id},
        UpdateExpression='SET #s = :s, aggregation_count = :a, completed_at = :t',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={
            ':s': 'COMPLETED',
            ':a': agg_count,
            ':t': int(time.time()),
        },
    )
