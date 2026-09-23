import json
import os
import time
import math
import boto3
from collections import defaultdict

DATA_LAKE_BUCKET = os.environ.get('DATA_LAKE_BUCKET', 'streamforge-lake')
ALERTS_TABLE = os.environ.get('ALERTS_TABLE', 'streamforge-alerts')
RUN_HISTORY_TABLE = os.environ.get('RUN_HISTORY_TABLE', 'streamforge-runs')

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
cloudwatch = boto3.client('cloudwatch')
alerts_table = dynamodb.Table(ALERTS_TABLE)
run_table = dynamodb.Table(RUN_HISTORY_TABLE)


def lambda_handler(event, context):
    pipeline_id = event['pipeline_id']
    run_id = event['run_id']
    clean_location = event.get('clean_location', event.get('raw_location', ''))
    pipeline_config = event.get('pipeline_config', {})

    events = load_events(clean_location)

    detect_steps = [
        step for step in pipeline_config.get('steps', [])
        if step.get('type') == 'detect_anomalies'
    ]

    anomaly_count = 0

    if detect_steps:
        for step in detect_steps:
            field = step.get('field', 'value')
            method = step.get('method', 'zscore')
            threshold = step.get('threshold', 2.5)
            contamination = step.get('contamination', 0.05)

            if method == 'isolation_forest':
                anomaly_count += detect_isolation_forest(events, field, contamination)
            elif method == 'zscore':
                anomaly_count += detect_zscore(events, field, threshold)
            elif method == 'iqr':
                anomaly_count += detect_iqr(events, field)
            elif method == 'mad':
                anomaly_count += detect_mad(events, field, threshold)
    else:
        numeric_fields = find_numeric_fields(events)
        for field in numeric_fields[:3]:
            anomaly_count += detect_zscore(events, field, 2.5)

    if anomaly_count > 0:
        anomalous = [e for e in events if e.get('is_anomaly')]
        create_alerts(pipeline_id, run_id, anomalous)

    write_results(events, pipeline_id, run_id)

    update_run_status(pipeline_id, run_id, anomaly_count)

    # Publish custom metrics to CloudWatch
    publish_metrics(pipeline_id, len(events), anomaly_count)

    return {
        'pipeline_id': pipeline_id,
        'run_id': run_id,
        'events_count': event.get('events_count', len(events)),
        'events_processed': len(events),
        'anomalies_detected': anomaly_count,
        'clean_location': clean_location,
        'pipeline_config': pipeline_config,
    }


def detect_zscore(events, field, threshold=2.5):
    values = extract_values(events, field)
    valid_values = [v for v in values if v is not None]
    if len(valid_values) < 5:
        return 0

    mean = sum(valid_values) / len(valid_values)
    variance = sum((v - mean) ** 2 for v in valid_values) / len(valid_values)
    std = math.sqrt(variance) if variance > 0 else 1

    count = 0
    for evt, val in zip(events, values):
        if val is not None:
            zscore = abs(val - mean) / std if std > 0 else 0
            if zscore > threshold:
                evt['is_anomaly'] = True
                evt['anomaly_score'] = round(zscore, 4)
                count += 1

    return count


def detect_iqr(events, field):
    values = sorted(v for v in extract_values(events, field) if v is not None)
    if len(values) < 10:
        return 0

    q1 = values[len(values) // 4]
    q3 = values[3 * len(values) // 4]
    iqr = q3 - q1

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    count = 0
    for evt in events:
        val = get_numeric_value(evt, field)
        if val is not None and (val < lower or val > upper):
            distance = max(abs(val - lower), abs(val - upper)) / (iqr if iqr > 0 else 1)
            evt['is_anomaly'] = True
            evt['anomaly_score'] = round(distance, 4)
            count += 1

    return count


def detect_mad(events, field, threshold=3.5):
    values = extract_values(events, field)
    valid_values = [v for v in values if v is not None]
    if len(valid_values) < 5:
        return 0

    median = sorted(valid_values)[len(valid_values) // 2]
    abs_deviations = sorted(abs(v - median) for v in valid_values)
    mad = abs_deviations[len(abs_deviations) // 2]

    if mad == 0:
        return 0

    count = 0
    for evt, val in zip(events, values):
        if val is not None:
            modified_zscore = 0.6745 * (val - median) / mad
            if abs(modified_zscore) > threshold:
                evt['is_anomaly'] = True
                evt['anomaly_score'] = round(abs(modified_zscore), 4)
                count += 1

    return count


def detect_isolation_forest(events, field, contamination=0.05):
    values = extract_values(events, field)
    valid_values = [v for v in values if v is not None]
    if len(valid_values) < 20:
        return detect_zscore(events, field, 2.5)

    valid_indices = [i for i, v in enumerate(values) if v is not None]
    n = len(valid_values)
    n_trees = 100
    sample_size = min(256, n)
    scores = [0.0] * n

    import random
    rng = random.Random(42)

    for _ in range(n_trees):
        sample_indices = rng.sample(range(n), min(sample_size, n))
        sample_vals = [valid_values[i] for i in sample_indices]

        for idx in range(n):
            depth = simulate_isolation(valid_values[idx], sample_vals, rng)
            scores[idx] += depth

    c_n = 2 * (math.log(sample_size - 1) + 0.5772156649) - (2 * (sample_size - 1) / sample_size)

    anomaly_scores = []
    for i in range(n):
        avg_depth = scores[i] / n_trees
        score = 2 ** (-avg_depth / c_n) if c_n > 0 else 0.5
        anomaly_scores.append(score)

    sorted_scores = sorted(anomaly_scores, reverse=True)
    n_anomalies = max(1, int(n * contamination))
    threshold = sorted_scores[min(n_anomalies, len(sorted_scores) - 1)]

    count = 0
    for score_idx, event_idx in enumerate(valid_indices):
        if anomaly_scores[score_idx] >= threshold:
            events[event_idx]['is_anomaly'] = True
            events[event_idx]['anomaly_score'] = round(anomaly_scores[score_idx], 4)
            count += 1

    return count


def simulate_isolation(value, sample, rng, max_depth=10):
    if len(sample) <= 1 or max_depth <= 0:
        return 0

    min_val = min(sample)
    max_val = max(sample)

    if min_val == max_val:
        return 0

    split = rng.uniform(min_val, max_val)

    if value < split:
        left = [v for v in sample if v < split]
        return 1 + simulate_isolation(value, left, rng, max_depth - 1)
    else:
        right = [v for v in sample if v >= split]
        return 1 + simulate_isolation(value, right, rng, max_depth - 1)


def extract_values(events, field):
    values = []
    for evt in events:
        val = get_numeric_value(evt, field)
        values.append(val)
    return values


def get_numeric_value(event, field):
    payload = event.get('payload', '{}')
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None
    else:
        data = payload

    val = data.get(field, event.get(field))
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return None
    return None


def find_numeric_fields(events):
    field_counts = defaultdict(int)
    for evt in events[:50]:
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
                field_counts[k] += 1

    return [f for f, c in sorted(field_counts.items(), key=lambda x: -x[1]) if c > 5]


def create_alerts(pipeline_id, run_id, anomalous_events):
    import uuid

    for evt in anomalous_events[:10]:
        alert_id = f'alert-{uuid.uuid4().hex[:12]}'
        alerts_table.put_item(Item={
            'pipeline_id': pipeline_id,
            'alert_id': alert_id,
            'run_id': run_id,
            'event_id': evt.get('event_id', ''),
            'anomaly_score': str(evt.get('anomaly_score', 0)),
            'event_type': evt.get('event_type', ''),
            'timestamp': evt.get('timestamp', int(time.time() * 1000)),
            'created_at': int(time.time()),
            'severity': 'HIGH' if evt.get('anomaly_score', 0) > 0.8 else 'MEDIUM',
            'ttl': int(time.time()) + (90 * 24 * 60 * 60),
        })


def write_results(events, pipeline_id, run_id):
    from datetime import datetime
    now = datetime.utcnow()
    key = f'clean/{pipeline_id}/year={now.year}/month={now.month:02d}/day={now.day:02d}/{run_id}-anomaly.json'

    s3.put_object(
        Bucket=DATA_LAKE_BUCKET,
        Key=key,
        Body=json.dumps(events, default=str),
        ContentType='application/json',
    )


def load_events(location):
    parts = location.replace('s3://', '').split('/', 1)
    obj = s3.get_object(Bucket=parts[0], Key=parts[1])
    content = obj['Body'].read().decode('utf-8')
    data = json.loads(content)
    return data if isinstance(data, list) else [data]


def update_run_status(pipeline_id, run_id, anomaly_count):
    run_table.update_item(
        Key={'pipeline_id': pipeline_id, 'run_id': run_id},
        UpdateExpression='SET anomaly_count = :a, anomaly_detected_at = :t',
        ExpressionAttributeValues={
            ':a': anomaly_count,
            ':t': int(time.time()),
        },
    )


def publish_metrics(pipeline_id, events_processed, anomalies_detected):
    """Publish custom metrics to CloudWatch for dashboard and alerting."""
    try:
        from datetime import datetime
        cloudwatch.put_metric_data(
            Namespace='StreamForge',
            MetricData=[
                {
                    'MetricName': 'EventsProcessed',
                    'Value': events_processed,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow(),
                    'Dimensions': [
                        {'Name': 'PipelineId', 'Value': pipeline_id},
                    ],
                },
                {
                    'MetricName': 'AnomaliesDetected',
                    'Value': anomalies_detected,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow(),
                    'Dimensions': [
                        {'Name': 'PipelineId', 'Value': pipeline_id},
                    ],
                },
                {
                    'MetricName': 'AnomalyRate',
                    'Value': (anomalies_detected / events_processed * 100) if events_processed > 0 else 0,
                    'Unit': 'Percent',
                    'Timestamp': datetime.utcnow(),
                    'Dimensions': [
                        {'Name': 'PipelineId', 'Value': pipeline_id},
                    ],
                },
            ],
        )
    except Exception as e:
        print(f'Failed to publish CloudWatch metrics: {e}')
