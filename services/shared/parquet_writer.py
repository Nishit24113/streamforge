import io
import json
import time
from datetime import datetime
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import boto3

from config import DATA_LAKE_BUCKET, get_client


RAW_SCHEMA = pa.schema([
    ('event_id', pa.string()),
    ('pipeline_id', pa.string()),
    ('timestamp', pa.int64()),
    ('source', pa.string()),
    ('event_type', pa.string()),
    ('payload', pa.string()),
    ('ingested_at', pa.int64()),
])

CLEAN_SCHEMA = pa.schema([
    ('event_id', pa.string()),
    ('pipeline_id', pa.string()),
    ('timestamp', pa.int64()),
    ('source', pa.string()),
    ('event_type', pa.string()),
    ('payload', pa.string()),
    ('processed_at', pa.int64()),
    ('is_anomaly', pa.bool_()),
    ('anomaly_score', pa.float64()),
])


def write_events_to_parquet(
    events: list[dict[str, Any]],
    zone: str,
    pipeline_id: str,
    run_id: str,
) -> str:
    if not events:
        return ''

    now = datetime.utcnow()
    partition = f'year={now.year}/month={now.month:02d}/day={now.day:02d}'

    schema = CLEAN_SCHEMA if zone == 'clean' else RAW_SCHEMA

    columns = {field.name: [] for field in schema}
    for event in events:
        for field in schema:
            columns[field.name].append(event.get(field.name))

    table = pa.table(columns, schema=schema)

    buf = io.BytesIO()
    pq.write_table(
        table,
        buf,
        compression='snappy',
        write_statistics=True,
        version='2.6',
    )

    s3_key = f'{zone}/{pipeline_id}/{partition}/{run_id}.parquet'

    s3 = get_client('s3')
    s3.put_object(
        Bucket=DATA_LAKE_BUCKET,
        Key=s3_key,
        Body=buf.getvalue(),
        ContentType='application/octet-stream',
    )

    return f's3://{DATA_LAKE_BUCKET}/{s3_key}'


def write_aggregations_to_parquet(
    aggregations: list[dict[str, Any]],
    pipeline_id: str,
    run_id: str,
) -> str:
    if not aggregations:
        return ''

    now = datetime.utcnow()
    partition = f'year={now.year}/month={now.month:02d}/day={now.day:02d}'

    field_names = set()
    for agg in aggregations:
        field_names.update(agg.keys())

    fields = []
    for name in sorted(field_names):
        sample = next((a[name] for a in aggregations if name in a), None)
        if isinstance(sample, (int, float)):
            fields.append((name, pa.float64()))
        else:
            fields.append((name, pa.string()))

    schema = pa.schema(fields)
    columns = {name: [agg.get(name) for agg in aggregations] for name, _ in fields}

    table = pa.table(columns, schema=schema)

    buf = io.BytesIO()
    pq.write_table(table, buf, compression='snappy')

    s3_key = f'agg/{pipeline_id}/{partition}/{run_id}.parquet'

    s3 = get_client('s3')
    s3.put_object(
        Bucket=DATA_LAKE_BUCKET,
        Key=s3_key,
        Body=buf.getvalue(),
        ContentType='application/octet-stream',
    )

    return f's3://{DATA_LAKE_BUCKET}/{s3_key}'
