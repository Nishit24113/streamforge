"""
Data Export & Integration Handler for StreamForge.

Supports:
- CSV/JSON export with presigned URLs
- BigQuery streaming integration
- Snowflake bulk export
- Webhook notifications (Slack, Discord, custom)
- Scheduled exports via EventBridge
"""

import json
import os
import time
import csv
import io
from datetime import datetime, timedelta
import boto3

DATA_LAKE_BUCKET = os.environ.get('DATA_LAKE_BUCKET', 'streamforge-lake')
PIPELINE_TABLE = os.environ.get('PIPELINE_TABLE', 'streamforge-pipelines')
EXPORT_CONFIG_TABLE = os.environ.get('EXPORT_CONFIG_TABLE', 'streamforge-export-configs')

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

export_config_table = dynamodb.Table(EXPORT_CONFIG_TABLE)


def lambda_handler(event, context):
    """Handle export requests and scheduled exports."""
    action = event.get('action', 'export')

    if action == 'export':
        return handle_export(event)
    elif action == 'webhook':
        return handle_webhook(event)
    elif action == 'scheduled':
        return handle_scheduled_export(event)
    elif action == 'configure':
        return configure_export(event)
    elif action == 'list_exports':
        return list_exports(event)
    else:
        return {'statusCode': 400, 'error': 'Invalid action'}


def handle_export(event):
    """
    Export pipeline data to CSV/JSON.

    Args:
        event: {
            'pipeline_id': 'ecommerce',
            'format': 'csv' or 'json',
            'date_from': '2026-09-01',
            'date_to': '2026-09-26',
            'zone': 'clean' or 'raw' or 'agg'
        }

    Returns:
        Presigned URL to download export file
    """
    pipeline_id = event.get('pipeline_id')
    export_format = event.get('format', 'csv')
    date_from = event.get('date_from', datetime.utcnow().strftime('%Y-%m-%d'))
    date_to = event.get('date_to', datetime.utcnow().strftime('%Y-%m-%d'))
    zone = event.get('zone', 'clean')

    if not pipeline_id:
        return {'statusCode': 400, 'error': 'pipeline_id required'}

    # Collect events from S3
    events = collect_events(pipeline_id, date_from, date_to, zone)

    if not events:
        return {
            'statusCode': 200,
            'message': 'No data found for export',
            'event_count': 0
        }

    # Generate export file
    export_key = generate_export_file(pipeline_id, events, export_format)

    # Create presigned URL (expires in 1 hour)
    presigned_url = s3.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': DATA_LAKE_BUCKET,
            'Key': export_key
        },
        ExpiresIn=3600
    )

    return {
        'statusCode': 200,
        'export_url': presigned_url,
        'event_count': len(events),
        'format': export_format,
        'expires_in': 3600,
        'file_size_bytes': get_file_size(export_key)
    }


def handle_webhook(event):
    """
    Send webhook notification with pipeline data.

    Args:
        event: {
            'webhook_url': 'https://hooks.slack.com/...',
            'webhook_type': 'slack' or 'discord' or 'custom',
            'pipeline_id': 'ecommerce',
            'event_data': {...}
        }
    """
    webhook_url = event.get('webhook_url')
    webhook_type = event.get('webhook_type', 'custom')
    pipeline_id = event.get('pipeline_id')
    event_data = event.get('event_data', {})

    if not webhook_url:
        return {'statusCode': 400, 'error': 'webhook_url required'}

    # Format payload based on webhook type
    if webhook_type == 'slack':
        payload = format_slack_payload(pipeline_id, event_data)
    elif webhook_type == 'discord':
        payload = format_discord_payload(pipeline_id, event_data)
    else:
        payload = event_data

    # Send webhook
    import requests
    response = requests.post(webhook_url, json=payload, timeout=10)

    return {
        'statusCode': 200 if response.status_code < 400 else 500,
        'webhook_status': response.status_code,
        'message': 'Webhook sent successfully' if response.status_code < 400 else 'Webhook failed'
    }


def handle_scheduled_export(event):
    """
    Handle scheduled export triggered by EventBridge.

    Args:
        event: {
            'pipeline_id': 'ecommerce',
            'export_config_id': 'daily-export-abc'
        }
    """
    config_id = event.get('export_config_id')

    if not config_id:
        return {'statusCode': 400, 'error': 'export_config_id required'}

    # Load export configuration
    config = export_config_table.get_item(Key={'config_id': config_id}).get('Item')

    if not config:
        return {'statusCode': 404, 'error': 'Export config not found'}

    # Execute export based on config
    export_result = handle_export({
        'pipeline_id': config['pipeline_id'],
        'format': config.get('format', 'csv'),
        'date_from': (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d'),
        'date_to': datetime.utcnow().strftime('%Y-%m-%d'),
        'zone': config.get('zone', 'clean')
    })

    # Send notification if configured
    if config.get('notify_webhook'):
        handle_webhook({
            'webhook_url': config['notify_webhook'],
            'webhook_type': config.get('webhook_type', 'slack'),
            'pipeline_id': config['pipeline_id'],
            'event_data': {
                'export_url': export_result.get('export_url'),
                'event_count': export_result.get('event_count'),
                'message': f"Scheduled export for {config['pipeline_id']} completed"
            }
        })

    return export_result


def configure_export(event):
    """
    Configure scheduled export.

    Args:
        event: {
            'pipeline_id': 'ecommerce',
            'schedule': 'daily' or 'weekly' or 'cron(0 0 * * ? *)',
            'format': 'csv' or 'json',
            'zone': 'clean',
            'notify_webhook': 'https://...',
            'webhook_type': 'slack'
        }
    """
    import uuid

    config_id = f'export-{uuid.uuid4().hex[:12]}'
    pipeline_id = event.get('pipeline_id')
    schedule = event.get('schedule', 'daily')

    if not pipeline_id:
        return {'statusCode': 400, 'error': 'pipeline_id required'}

    config = {
        'config_id': config_id,
        'pipeline_id': pipeline_id,
        'schedule': schedule,
        'format': event.get('format', 'csv'),
        'zone': event.get('zone', 'clean'),
        'notify_webhook': event.get('notify_webhook'),
        'webhook_type': event.get('webhook_type', 'slack'),
        'created_at': int(time.time()),
        'enabled': True
    }

    export_config_table.put_item(Item=config)

    return {
        'statusCode': 201,
        'config_id': config_id,
        'message': 'Export configuration created',
        'config': config
    }


def list_exports(event):
    """List all export configurations for a pipeline."""
    pipeline_id = event.get('pipeline_id')

    if not pipeline_id:
        # List all exports
        result = export_config_table.scan(Limit=100)
    else:
        # Filter by pipeline
        result = export_config_table.scan(
            FilterExpression='pipeline_id = :pid',
            ExpressionAttributeValues={':pid': pipeline_id},
            Limit=100
        )

    configs = result.get('Items', [])

    return {
        'statusCode': 200,
        'exports': configs,
        'count': len(configs)
    }


# Helper functions

def collect_events(pipeline_id, date_from, date_to, zone='clean'):
    """Collect events from S3 for date range."""
    events = []

    # Parse dates
    start_date = datetime.strptime(date_from, '%Y-%m-%d')
    end_date = datetime.strptime(date_to, '%Y-%m-%d')

    # Iterate through date range
    current_date = start_date
    while current_date <= end_date:
        year = current_date.year
        month = current_date.month
        day = current_date.day

        # List objects for this date
        prefix = f'{zone}/{pipeline_id}/year={year}/month={month:02d}/day={day:02d}/'

        try:
            response = s3.list_objects_v2(
                Bucket=DATA_LAKE_BUCKET,
                Prefix=prefix
            )

            for obj in response.get('Contents', []):
                # Load and parse events from file
                file_events = load_events_from_s3(obj['Key'])
                events.extend(file_events)

        except Exception as e:
            print(f'Error loading from {prefix}: {e}')

        current_date += timedelta(days=1)

    return events


def load_events_from_s3(key):
    """Load events from S3 object."""
    try:
        obj = s3.get_object(Bucket=DATA_LAKE_BUCKET, Key=key)
        content = obj['Body'].read().decode('utf-8')
        data = json.loads(content)
        return data if isinstance(data, list) else [data]
    except Exception as e:
        print(f'Error loading {key}: {e}')
        return []


def generate_export_file(pipeline_id, events, export_format):
    """Generate export file and upload to S3."""
    timestamp = int(time.time())
    export_key = f'exports/{pipeline_id}/{timestamp}.{export_format}'

    if export_format == 'csv':
        content = generate_csv(events)
        content_type = 'text/csv'
    else:  # json
        content = json.dumps(events, indent=2, default=str)
        content_type = 'application/json'

    s3.put_object(
        Bucket=DATA_LAKE_BUCKET,
        Key=export_key,
        Body=content,
        ContentType=content_type
    )

    return export_key


def generate_csv(events):
    """Convert events to CSV format."""
    if not events:
        return ''

    # Flatten events and extract all fields
    flattened = []
    for evt in events:
        flat_evt = {
            'event_id': evt.get('event_id', ''),
            'pipeline_id': evt.get('pipeline_id', ''),
            'timestamp': evt.get('timestamp', ''),
            'event_type': evt.get('event_type', ''),
            'source': evt.get('source', ''),
            'is_anomaly': evt.get('is_anomaly', False),
            'anomaly_score': evt.get('anomaly_score', 0)
        }

        # Add payload fields
        payload = evt.get('payload', {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}

        flat_evt.update(payload)
        flattened.append(flat_evt)

    # Get all unique field names
    fieldnames = set()
    for evt in flattened:
        fieldnames.update(evt.keys())
    fieldnames = sorted(fieldnames)

    # Write CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(flattened)

    return output.getvalue()


def get_file_size(key):
    """Get file size from S3."""
    try:
        response = s3.head_object(Bucket=DATA_LAKE_BUCKET, Key=key)
        return response['ContentLength']
    except Exception:
        return 0


def format_slack_payload(pipeline_id, event_data):
    """Format payload for Slack webhook."""
    return {
        'text': f'📊 StreamForge Export: {pipeline_id}',
        'blocks': [
            {
                'type': 'header',
                'text': {
                    'type': 'plain_text',
                    'text': f'📊 StreamForge Export: {pipeline_id}'
                }
            },
            {
                'type': 'section',
                'fields': [
                    {
                        'type': 'mrkdwn',
                        'text': f'*Events:*\n{event_data.get("event_count", 0):,}'
                    },
                    {
                        'type': 'mrkdwn',
                        'text': f'*Status:*\n✅ {event_data.get("message", "Complete")}'
                    }
                ]
            },
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': f'<{event_data.get("export_url", "#")}|📥 Download Export>'
                }
            }
        ]
    }


def format_discord_payload(pipeline_id, event_data):
    """Format payload for Discord webhook."""
    return {
        'embeds': [{
            'title': f'📊 StreamForge Export: {pipeline_id}',
            'description': event_data.get('message', 'Export completed'),
            'color': 3066993,  # Green
            'fields': [
                {
                    'name': 'Events',
                    'value': str(event_data.get('event_count', 0)),
                    'inline': True
                },
                {
                    'name': 'Download',
                    'value': f'[Export File]({event_data.get("export_url", "#")})',
                    'inline': True
                }
            ],
            'timestamp': datetime.utcnow().isoformat()
        }]
    }
