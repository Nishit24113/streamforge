import json
import os
import time
import uuid
import hashlib
import hmac
import boto3

KINESIS_STREAM = os.environ.get('KINESIS_STREAM', 'streamforge-events')
PIPELINE_TABLE = os.environ.get('PIPELINE_TABLE', 'streamforge-pipelines')

kinesis = boto3.client('kinesis')
dynamodb = boto3.resource('dynamodb')
pipeline_table = dynamodb.Table(PIPELINE_TABLE)

WEBHOOK_PARSERS = {
    'github': parse_github,
    'stripe': parse_stripe,
    'generic': parse_generic,
}


def lambda_handler(event, context):
    path_params = event.get('pathParameters') or {}
    pipeline_id = path_params.get('pipeline_id', 'default')

    try:
        pipeline = pipeline_table.get_item(
            Key={'pipeline_id': pipeline_id}
        ).get('Item')

        if not pipeline:
            return response(404, {'error': f'Pipeline {pipeline_id} not found'})

        webhook_config = pipeline.get('source', {})
        webhook_type = webhook_config.get('webhook_type', 'generic')

        secret = webhook_config.get('secret')
        if secret:
            if not verify_signature(event, secret, webhook_type):
                return response(401, {'error': 'Invalid webhook signature'})

        body = json.loads(event.get('body', '{}'))
        headers = event.get('headers', {})

        parser = WEBHOOK_PARSERS.get(webhook_type, parse_generic)
        events = parser(body, headers)

        now = int(time.time() * 1000)
        run_id = f'wh-{uuid.uuid4().hex[:12]}'

        records = []
        for evt in events:
            record = {
                'event_id': evt.get('event_id', f'evt-{uuid.uuid4().hex[:12]}'),
                'pipeline_id': pipeline_id,
                'timestamp': evt.get('timestamp', now),
                'source': f'webhook:{webhook_type}',
                'event_type': evt.get('event_type', 'webhook'),
                'payload': json.dumps(evt),
                'ingested_at': now,
                'run_id': run_id,
            }
            records.append({
                'Data': json.dumps(record).encode('utf-8'),
                'PartitionKey': pipeline_id,
            })

        if records:
            kinesis.put_records(
                StreamName=KINESIS_STREAM,
                Records=records[:100],
            )

        return response(200, {
            'status': 'accepted',
            'pipeline': pipeline_id,
            'events_received': len(records),
            'run_id': run_id,
        })

    except json.JSONDecodeError:
        return response(400, {'error': 'Invalid JSON body'})
    except Exception as e:
        return response(500, {'error': str(e)})


def parse_github(body, headers):
    event_type = headers.get('X-GitHub-Event', headers.get('x-github-event', 'unknown'))
    delivery_id = headers.get('X-GitHub-Delivery', headers.get('x-github-delivery', ''))

    events = [{
        'event_id': delivery_id or f'gh-{uuid.uuid4().hex[:12]}',
        'event_type': f'github.{event_type}',
        'timestamp': int(time.time() * 1000),
        'repo': body.get('repository', {}).get('full_name', ''),
        'sender': body.get('sender', {}).get('login', ''),
        'action': body.get('action', ''),
        'data': body,
    }]

    if event_type == 'push':
        for commit in body.get('commits', []):
            events.append({
                'event_id': commit.get('id', ''),
                'event_type': 'github.commit',
                'timestamp': int(time.time() * 1000),
                'author': commit.get('author', {}).get('name', ''),
                'message': commit.get('message', ''),
                'files_changed': len(commit.get('added', []))
                    + len(commit.get('modified', []))
                    + len(commit.get('removed', [])),
            })

    return events


def parse_stripe(body, headers):
    return [{
        'event_id': body.get('id', f'stripe-{uuid.uuid4().hex[:12]}'),
        'event_type': f"stripe.{body.get('type', 'unknown')}",
        'timestamp': body.get('created', int(time.time())) * 1000,
        'data': body.get('data', {}).get('object', {}),
        'livemode': body.get('livemode', False),
    }]


def parse_generic(body, headers):
    if isinstance(body, list):
        return [{'event_type': 'webhook', 'data': item, **item} for item in body]
    return [{'event_type': 'webhook', 'data': body, **body}]


def verify_signature(event, secret, webhook_type):
    body = event.get('body', '')
    headers = event.get('headers', {})

    if webhook_type == 'github':
        signature = headers.get('X-Hub-Signature-256', headers.get('x-hub-signature-256', ''))
        if not signature:
            return False
        expected = 'sha256=' + hmac.new(
            secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    if webhook_type == 'stripe':
        sig_header = headers.get('Stripe-Signature', headers.get('stripe-signature', ''))
        return bool(sig_header)

    return True


def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
        },
        'body': json.dumps(body, default=str),
    }
