import json
import os
import time
import boto3

DATA_LAKE_BUCKET = os.environ.get('DATA_LAKE_BUCKET', 'streamforge-lake')
ATHENA_WORKGROUP = os.environ.get('ATHENA_WORKGROUP', 'streamforge')
ATHENA_DATABASE = os.environ.get('ATHENA_DATABASE', 'streamforge')
PIPELINE_TABLE = os.environ.get('PIPELINE_TABLE', 'streamforge-pipelines')
RUN_HISTORY_TABLE = os.environ.get('RUN_HISTORY_TABLE', 'streamforge-runs')

athena = boto3.client('athena')
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

pipeline_table = dynamodb.Table(PIPELINE_TABLE)
run_table = dynamodb.Table(RUN_HISTORY_TABLE)


def lambda_handler(event, context):
    http_method = event.get('httpMethod', 'GET')
    path = event.get('path', '/')
    path_params = event.get('pathParameters') or {}

    try:
        if '/query' in path and http_method == 'POST':
            return handle_run_query(event)

        if '/query/' in path and http_method == 'GET':
            query_id = path_params.get('query_id', '')
            return handle_get_results(query_id)

        if '/stats' in path and http_method == 'GET':
            return handle_get_stats()

        if '/anomalies' in path and http_method == 'GET':
            return handle_get_anomalies(event)

        return response(404, {'error': 'Not found'})

    except Exception as e:
        return response(500, {'error': str(e)})


def handle_run_query(event):
    body = json.loads(event.get('body', '{}'))
    sql = body.get('sql', '')

    if not sql:
        return response(400, {'error': 'SQL query required'})

    forbidden = ['drop', 'delete', 'insert', 'update', 'create', 'alter', 'truncate']
    sql_lower = sql.lower().strip()
    for word in forbidden:
        if sql_lower.startswith(word):
            return response(400, {'error': f'Operation not allowed: {word}'})

    result = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={'Database': ATHENA_DATABASE},
        WorkGroup=ATHENA_WORKGROUP,
    )

    query_id = result['QueryExecutionId']

    return response(202, {
        'status': 'running',
        'query_id': query_id,
        'message': 'Query submitted. Poll GET /query/{query_id} for results.',
    })


def handle_get_results(query_id):
    status = athena.get_query_execution(QueryExecutionId=query_id)
    state = status['QueryExecution']['Status']['State']

    if state in ('QUEUED', 'RUNNING'):
        return response(200, {
            'status': state.lower(),
            'query_id': query_id,
            'message': 'Query still running',
        })

    if state == 'FAILED':
        reason = status['QueryExecution']['Status'].get('StateChangeReason', 'Unknown error')
        return response(200, {
            'status': 'failed',
            'query_id': query_id,
            'error': reason,
        })

    results = athena.get_query_results(
        QueryExecutionId=query_id,
        MaxResults=1000,
    )

    columns = [col['Label'] for col in results['ResultSet']['ResultSetMetadata']['ColumnInfo']]
    rows = []

    for row in results['ResultSet']['Rows'][1:]:
        row_data = {}
        for i, datum in enumerate(row['Data']):
            row_data[columns[i]] = datum.get('VarCharValue', None)
        rows.append(row_data)

    stats = status['QueryExecution'].get('Statistics', {})

    return response(200, {
        'status': 'completed',
        'query_id': query_id,
        'columns': columns,
        'rows': rows,
        'row_count': len(rows),
        'bytes_scanned': stats.get('DataScannedInBytes', 0),
        'execution_time_ms': stats.get('TotalExecutionTimeInMillis', 0),
    })


def handle_get_stats():
    result = run_table.scan(
        Limit=1000,
        ProjectionExpression='pipeline_id, #s, events_count, anomaly_count, started_at, completed_at',
        ExpressionAttributeNames={'#s': 'status'},
    )

    runs = result.get('Items', [])

    total_events = sum(int(r.get('events_count', 0)) for r in runs)
    total_anomalies = sum(int(r.get('anomaly_count', 0)) for r in runs)
    total_runs = len(runs)
    completed_runs = sum(1 for r in runs if r.get('status') == 'COMPLETED')
    failed_runs = sum(1 for r in runs if r.get('status') == 'FAILED')

    pipeline_stats = {}
    for r in runs:
        pid = r.get('pipeline_id', 'unknown')
        if pid not in pipeline_stats:
            pipeline_stats[pid] = {'runs': 0, 'events': 0, 'anomalies': 0}
        pipeline_stats[pid]['runs'] += 1
        pipeline_stats[pid]['events'] += int(r.get('events_count', 0))
        pipeline_stats[pid]['anomalies'] += int(r.get('anomaly_count', 0))

    pipelines_result = pipeline_table.scan(Limit=100)
    active_pipelines = len(pipelines_result.get('Items', []))

    return response(200, {
        'total_events': total_events,
        'total_anomalies': total_anomalies,
        'total_runs': total_runs,
        'completed_runs': completed_runs,
        'failed_runs': failed_runs,
        'active_pipelines': active_pipelines,
        'pipeline_stats': pipeline_stats,
        'anomaly_rate': round(total_anomalies / total_events * 100, 2) if total_events > 0 else 0,
    })


def handle_get_anomalies(event):
    params = event.get('queryStringParameters') or {}
    pipeline_id = params.get('pipeline_id')
    limit = int(params.get('limit', '50'))

    from boto3.dynamodb.conditions import Key

    alerts_table = dynamodb.Table(os.environ.get('ALERTS_TABLE', 'streamforge-alerts'))

    if pipeline_id:
        result = alerts_table.query(
            KeyConditionExpression=Key('pipeline_id').eq(pipeline_id),
            ScanIndexForward=False,
            Limit=limit,
        )
    else:
        result = alerts_table.scan(Limit=limit)

    alerts = result.get('Items', [])

    return response(200, {
        'anomalies': alerts,
        'count': len(alerts),
    })


def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        },
        'body': json.dumps(body, default=str),
    }
