"""
Data Quality Metrics for StreamForge Pipelines.

Monitors:
- Completeness: Percentage of non-null fields
- Freshness: Data recency and ingestion lag
- Accuracy: Type correctness, range validation, format compliance
- Schema drift: Unexpected fields or type changes
- Uniqueness: Duplicate detection
"""

import json
import os
import time
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import boto3

PIPELINE_TABLE = os.environ.get('PIPELINE_TABLE', 'streamforge-pipelines')
RUN_HISTORY_TABLE = os.environ.get('RUN_HISTORY_TABLE', 'streamforge-runs')
DATA_LAKE_BUCKET = os.environ.get('DATA_LAKE_BUCKET', 'streamforge-lake')
QUALITY_METRICS_TABLE = os.environ.get('QUALITY_METRICS_TABLE', 'streamforge-quality-metrics')

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
cloudwatch = boto3.client('cloudwatch')

quality_table = dynamodb.Table(QUALITY_METRICS_TABLE)
pipeline_table = dynamodb.Table(PIPELINE_TABLE)


def lambda_handler(event, context):
    """Calculate data quality metrics for a pipeline run."""
    action = event.get('action', 'calculate')
    pipeline_id = event.get('pipeline_id')
    run_id = event.get('run_id')

    if action == 'calculate':
        return calculate_quality_metrics(pipeline_id, run_id, event)
    elif action == 'get_metrics':
        return get_quality_metrics(pipeline_id)
    elif action == 'get_trends':
        return get_quality_trends(pipeline_id, event.get('hours', 24))
    else:
        return {'statusCode': 400, 'error': 'Invalid action'}


def calculate_quality_metrics(pipeline_id, run_id, event):
    """Calculate comprehensive data quality metrics."""
    clean_location = event.get('clean_location', '')
    expected_schema = event.get('expected_schema', {})

    # Load events from S3
    events = load_events_from_s3(clean_location)

    if not events:
        return {
            'statusCode': 200,
            'pipeline_id': pipeline_id,
            'run_id': run_id,
            'quality_score': 0,
            'message': 'No events to analyze'
        }

    # Calculate metrics
    completeness = calculate_completeness(events, expected_schema)
    freshness = calculate_freshness(events)
    accuracy = calculate_accuracy(events, expected_schema)
    uniqueness = calculate_uniqueness(events)
    schema_health = detect_schema_drift(events, expected_schema)

    # Overall quality score (weighted average)
    quality_score = (
        completeness['score'] * 0.25 +
        freshness['score'] * 0.20 +
        accuracy['score'] * 0.30 +
        uniqueness['score'] * 0.15 +
        schema_health['score'] * 0.10
    )

    metrics = {
        'pipeline_id': pipeline_id,
        'run_id': run_id,
        'timestamp': int(time.time()),
        'quality_score': round(quality_score, 2),
        'event_count': len(events),
        'completeness': completeness,
        'freshness': freshness,
        'accuracy': accuracy,
        'uniqueness': uniqueness,
        'schema_health': schema_health,
    }

    # Store metrics
    quality_table.put_item(Item={
        **metrics,
        'ttl': int(time.time()) + (90 * 24 * 60 * 60),  # 90 days
    })

    # Publish to CloudWatch
    publish_cloudwatch_metrics(pipeline_id, metrics)

    return {
        'statusCode': 200,
        **metrics
    }


def calculate_completeness(events, expected_schema):
    """
    Measure completeness: percentage of non-null required fields.

    Score:
    - 100: All required fields present in all events
    - 75-99: Most required fields present
    - 50-74: Half of required fields present
    - <50: Many missing fields
    """
    if not expected_schema:
        # No schema defined - check all fields
        all_fields = set()
        for evt in events:
            payload = get_payload(evt)
            all_fields.update(payload.keys())
        required_fields = list(all_fields)
    else:
        required_fields = list(expected_schema.keys())

    if not required_fields:
        return {'score': 100, 'missing_fields': {}, 'completeness_rate': 1.0}

    field_counts = defaultdict(int)
    for evt in events:
        payload = get_payload(evt)
        for field in required_fields:
            if field in payload and payload[field] is not None:
                field_counts[field] += 1

    total_events = len(events)
    completeness_rates = {
        field: field_counts[field] / total_events
        for field in required_fields
    }

    avg_completeness = sum(completeness_rates.values()) / len(completeness_rates)
    score = avg_completeness * 100

    # Find fields with <90% completeness
    missing_fields = {
        field: f'{(1 - rate) * 100:.1f}% missing'
        for field, rate in completeness_rates.items()
        if rate < 0.9
    }

    return {
        'score': round(score, 2),
        'completeness_rate': round(avg_completeness, 3),
        'missing_fields': missing_fields,
        'field_completeness': {k: round(v, 3) for k, v in completeness_rates.items()}
    }


def calculate_freshness(events):
    """
    Measure freshness: data recency and ingestion lag.

    Score:
    - 100: Data <5 minutes old
    - 90: Data <1 hour old
    - 70: Data <6 hours old
    - 50: Data <24 hours old
    - <50: Data >24 hours old
    """
    now = int(time.time() * 1000)
    timestamps = []

    for evt in events:
        timestamp = evt.get('timestamp', evt.get('ingested_at', now))
        timestamps.append(timestamp)

    if not timestamps:
        return {'score': 0, 'avg_age_seconds': 0, 'max_age_seconds': 0}

    avg_timestamp = sum(timestamps) / len(timestamps)
    max_timestamp = max(timestamps)
    min_timestamp = min(timestamps)

    avg_age_ms = now - avg_timestamp
    max_age_ms = now - min_timestamp
    avg_age_seconds = avg_age_ms / 1000
    max_age_seconds = max_age_ms / 1000

    # Score based on average age
    if avg_age_seconds < 300:  # <5 minutes
        score = 100
    elif avg_age_seconds < 3600:  # <1 hour
        score = 90
    elif avg_age_seconds < 21600:  # <6 hours
        score = 70
    elif avg_age_seconds < 86400:  # <24 hours
        score = 50
    else:
        score = max(0, 50 - (avg_age_seconds - 86400) / 86400 * 10)

    return {
        'score': round(score, 2),
        'avg_age_seconds': round(avg_age_seconds, 1),
        'max_age_seconds': round(max_age_seconds, 1),
        'min_timestamp': min_timestamp,
        'max_timestamp': max_timestamp,
        'is_fresh': avg_age_seconds < 3600
    }


def calculate_accuracy(events, expected_schema):
    """
    Measure accuracy: type correctness, range validation, format compliance.

    Score:
    - 100: All values match expected types and ranges
    - 90-99: Most values correct
    - 70-89: Some type/range violations
    - <70: Many incorrect values
    """
    if not expected_schema:
        return {'score': 100, 'violations': [], 'accuracy_rate': 1.0}

    violations = []
    total_checks = 0

    for i, evt in enumerate(events):
        payload = get_payload(evt)

        for field, expected_type in expected_schema.items():
            if field not in payload:
                continue

            value = payload[field]
            total_checks += 1

            # Type checking
            if expected_type == 'string' and not isinstance(value, str):
                violations.append({
                    'event_index': i,
                    'field': field,
                    'expected': 'string',
                    'actual': type(value).__name__,
                    'value': str(value)[:50]
                })
            elif expected_type == 'number' and not isinstance(value, (int, float)):
                violations.append({
                    'event_index': i,
                    'field': field,
                    'expected': 'number',
                    'actual': type(value).__name__,
                    'value': str(value)[:50]
                })
            elif expected_type == 'boolean' and not isinstance(value, bool):
                violations.append({
                    'event_index': i,
                    'field': field,
                    'expected': 'boolean',
                    'actual': type(value).__name__,
                    'value': str(value)[:50]
                })

    if total_checks == 0:
        return {'score': 100, 'violations': [], 'accuracy_rate': 1.0}

    accuracy_rate = 1 - (len(violations) / total_checks)
    score = accuracy_rate * 100

    return {
        'score': round(score, 2),
        'accuracy_rate': round(accuracy_rate, 3),
        'violations': violations[:10],  # Limit to first 10
        'total_violations': len(violations)
    }


def calculate_uniqueness(events):
    """
    Measure uniqueness: duplicate detection.

    Score:
    - 100: No duplicates
    - 90: <5% duplicates
    - 70: <15% duplicates
    - <70: High duplicate rate
    """
    event_ids = [evt.get('event_id', '') for evt in events]
    unique_ids = set(event_ids)

    total = len(event_ids)
    unique = len(unique_ids)
    duplicates = total - unique
    duplicate_rate = duplicates / total if total > 0 else 0

    if duplicate_rate == 0:
        score = 100
    elif duplicate_rate < 0.05:
        score = 90
    elif duplicate_rate < 0.15:
        score = 70
    else:
        score = max(0, 70 - duplicate_rate * 100)

    return {
        'score': round(score, 2),
        'total_events': total,
        'unique_events': unique,
        'duplicate_count': duplicates,
        'duplicate_rate': round(duplicate_rate, 3)
    }


def detect_schema_drift(events, expected_schema):
    """
    Detect schema drift: unexpected fields or type changes.

    Score:
    - 100: Schema stable, no drift
    - 90: Minor drift (new optional fields)
    - 70: Moderate drift (type changes)
    - <70: Major drift (missing required fields)
    """
    if not expected_schema:
        return {'score': 100, 'drift_detected': False, 'new_fields': [], 'type_changes': []}

    all_fields = set()
    field_types = defaultdict(Counter)

    for evt in events:
        payload = get_payload(evt)
        all_fields.update(payload.keys())

        for field, value in payload.items():
            field_types[field][type(value).__name__] += 1

    # Detect new fields
    expected_fields = set(expected_schema.keys())
    new_fields = list(all_fields - expected_fields)

    # Detect type changes (field has multiple types)
    type_changes = []
    for field, types in field_types.items():
        if len(types) > 1:
            type_changes.append({
                'field': field,
                'types': dict(types)
            })

    # Scoring
    drift_score = 100
    if new_fields:
        drift_score -= len(new_fields) * 2  # -2 per new field
    if type_changes:
        drift_score -= len(type_changes) * 10  # -10 per type change

    drift_score = max(0, drift_score)

    return {
        'score': round(drift_score, 2),
        'drift_detected': bool(new_fields or type_changes),
        'new_fields': new_fields,
        'type_changes': type_changes,
        'schema_stability': 'stable' if drift_score > 90 else 'drift_detected'
    }


def get_quality_metrics(pipeline_id):
    """Get latest quality metrics for a pipeline."""
    result = quality_table.query(
        KeyConditionExpression='pipeline_id = :pid',
        ExpressionAttributeValues={':pid': pipeline_id},
        ScanIndexForward=False,
        Limit=1
    )

    items = result.get('Items', [])
    if not items:
        return {'statusCode': 404, 'error': 'No quality metrics found'}

    return {'statusCode': 200, 'metrics': items[0]}


def get_quality_trends(pipeline_id, hours=24):
    """Get quality score trends over time."""
    cutoff = int(time.time()) - (hours * 3600)

    result = quality_table.query(
        KeyConditionExpression='pipeline_id = :pid AND #ts > :cutoff',
        ExpressionAttributeNames={'#ts': 'timestamp'},
        ExpressionAttributeValues={':pid': pipeline_id, ':cutoff': cutoff},
        ScanIndexForward=False,
        Limit=100
    )

    items = result.get('Items', [])

    # Extract trends
    scores = [item['quality_score'] for item in items]
    timestamps = [item['timestamp'] for item in items]

    if not scores:
        return {'statusCode': 200, 'pipeline_id': pipeline_id, 'data_points': 0}

    return {
        'statusCode': 200,
        'pipeline_id': pipeline_id,
        'time_window_hours': hours,
        'data_points': len(scores),
        'avg_quality_score': round(sum(scores) / len(scores), 2),
        'min_quality_score': min(scores),
        'max_quality_score': max(scores),
        'latest_score': scores[0],
        'trend': 'improving' if len(scores) > 1 and scores[0] > scores[-1] else 'declining',
        'history': [{'timestamp': ts, 'score': sc} for ts, sc in zip(timestamps, scores)]
    }


def load_events_from_s3(location):
    """Load events from S3 location."""
    if not location:
        return []

    parts = location.replace('s3://', '').split('/', 1)
    try:
        obj = s3.get_object(Bucket=parts[0], Key=parts[1])
        content = obj['Body'].read().decode('utf-8')
        data = json.loads(content)
        return data if isinstance(data, list) else [data]
    except Exception as e:
        print(f'Error loading from S3: {e}')
        return []


def get_payload(event):
    """Extract payload from event."""
    payload = event.get('payload', {})
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}
    return payload


def publish_cloudwatch_metrics(pipeline_id, metrics):
    """Publish quality metrics to CloudWatch."""
    try:
        cloudwatch.put_metric_data(
            Namespace='StreamForge/DataQuality',
            MetricData=[
                {
                    'MetricName': 'QualityScore',
                    'Value': metrics['quality_score'],
                    'Unit': 'None',
                    'Timestamp': datetime.utcnow(),
                    'Dimensions': [{'Name': 'PipelineId', 'Value': pipeline_id}],
                },
                {
                    'MetricName': 'CompletenessScore',
                    'Value': metrics['completeness']['score'],
                    'Unit': 'None',
                    'Timestamp': datetime.utcnow(),
                    'Dimensions': [{'Name': 'PipelineId', 'Value': pipeline_id}],
                },
                {
                    'MetricName': 'FreshnessScore',
                    'Value': metrics['freshness']['score'],
                    'Unit': 'None',
                    'Timestamp': datetime.utcnow(),
                    'Dimensions': [{'Name': 'PipelineId', 'Value': pipeline_id}],
                },
                {
                    'MetricName': 'AccuracyScore',
                    'Value': metrics['accuracy']['score'],
                    'Unit': 'None',
                    'Timestamp': datetime.utcnow(),
                    'Dimensions': [{'Name': 'PipelineId', 'Value': pipeline_id}],
                },
            ],
        )
    except Exception as e:
        print(f'Failed to publish CloudWatch metrics: {e}')
