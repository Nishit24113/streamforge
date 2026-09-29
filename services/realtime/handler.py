"""
Real-Time WebSocket Handler for StreamForge.

Streams live metrics, events, and anomalies to connected dashboards.
Supports multiple concurrent connections with pipeline-specific subscriptions.
"""

import json
import time
from typing import Dict, Set
import boto3
from aws_lambda_powertools import Logger

logger = Logger()

# Store active connections (in production, use DynamoDB or Redis)
connections: Dict[str, Set[str]] = {}  # {pipeline_id: {connection_id, ...}}

# AWS clients
dynamodb = boto3.resource('dynamodb')
apigateway = boto3.client('apigatewaymanagementapi')


def lambda_handler(event, context):
    """
    WebSocket Lambda handler for API Gateway WebSocket routes.

    Supported routes:
    - $connect: Client connects to WebSocket
    - $disconnect: Client disconnects
    - subscribe: Client subscribes to pipeline updates
    - $default: Catch-all for other messages
    """
    route_key = event.get('requestContext', {}).get('routeKey')
    connection_id = event.get('requestContext', {}).get('connectionId')

    if route_key == '$connect':
        return handle_connect(connection_id, event)
    elif route_key == '$disconnect':
        return handle_disconnect(connection_id)
    elif route_key == 'subscribe':
        return handle_subscribe(connection_id, event)
    else:
        return {'statusCode': 400, 'body': 'Unknown route'}


def handle_connect(connection_id: str, event: dict) -> dict:
    """Handle new WebSocket connection."""
    logger.info(f"Client connected: {connection_id}")

    # Extract pipeline_id from query parameters
    pipeline_id = event.get('queryStringParameters', {}).get('pipeline')

    if not pipeline_id:
        return {'statusCode': 400, 'body': 'Missing pipeline parameter'}

    # Add connection to pipeline subscription
    if pipeline_id not in connections:
        connections[pipeline_id] = set()

    connections[pipeline_id].add(connection_id)

    logger.info(f"Connection {connection_id} subscribed to pipeline {pipeline_id}")

    return {'statusCode': 200, 'body': 'Connected'}


def handle_disconnect(connection_id: str) -> dict:
    """Handle WebSocket disconnection."""
    logger.info(f"Client disconnected: {connection_id}")

    # Remove connection from all pipelines
    for pipeline_id, conn_set in connections.items():
        conn_set.discard(connection_id)

    return {'statusCode': 200, 'body': 'Disconnected'}


def handle_subscribe(connection_id: str, event: dict) -> dict:
    """Handle subscription message."""
    try:
        body = json.loads(event.get('body', '{}'))
        pipeline_id = body.get('pipeline_id')

        if not pipeline_id:
            return {'statusCode': 400, 'body': 'Missing pipeline_id'}

        # Add connection to pipeline
        if pipeline_id not in connections:
            connections[pipeline_id] = set()

        connections[pipeline_id].add(connection_id)

        logger.info(f"Connection {connection_id} subscribed to pipeline {pipeline_id}")

        return {'statusCode': 200, 'body': 'Subscribed'}

    except Exception as e:
        logger.error(f"Error handling subscribe: {e}")
        return {'statusCode': 500, 'body': str(e)}


def broadcast_event(pipeline_id: str, event_data: dict, endpoint_url: str):
    """
    Broadcast event to all connected clients subscribed to pipeline.

    Args:
        pipeline_id: Pipeline identifier
        event_data: Event data to broadcast
        endpoint_url: API Gateway WebSocket endpoint URL
    """
    if pipeline_id not in connections:
        return

    # Get API Gateway Management API client
    apigw_management = boto3.client(
        'apigatewaymanagementapi',
        endpoint_url=endpoint_url
    )

    # Message payload
    message = json.dumps({
        'type': 'event',
        'event': event_data
    })

    # Broadcast to all connections
    dead_connections = set()

    for connection_id in connections[pipeline_id]:
        try:
            apigw_management.post_to_connection(
                ConnectionId=connection_id,
                Data=message.encode('utf-8')
            )
        except apigw_management.exceptions.GoneException:
            # Connection is dead, mark for removal
            dead_connections.add(connection_id)
        except Exception as e:
            logger.error(f"Error broadcasting to {connection_id}: {e}")

    # Clean up dead connections
    connections[pipeline_id] -= dead_connections


def broadcast_metrics(pipeline_id: str, metrics: dict, endpoint_url: str):
    """
    Broadcast real-time metrics to all connected clients.

    Args:
        pipeline_id: Pipeline identifier
        metrics: Metrics data (eventsPerSecond, anomalyRate, etc.)
        endpoint_url: API Gateway WebSocket endpoint URL
    """
    if pipeline_id not in connections:
        return

    apigw_management = boto3.client(
        'apigatewaymanagementapi',
        endpoint_url=endpoint_url
    )

    message = json.dumps({
        'type': 'metrics',
        'metrics': metrics
    })

    dead_connections = set()

    for connection_id in connections[pipeline_id]:
        try:
            apigw_management.post_to_connection(
                ConnectionId=connection_id,
                Data=message.encode('utf-8')
            )
        except apigw_management.exceptions.GoneException:
            dead_connections.add(connection_id)
        except Exception as e:
            logger.error(f"Error broadcasting metrics to {connection_id}: {e}")

    connections[pipeline_id] -= dead_connections


def calculate_realtime_metrics(pipeline_id: str) -> dict:
    """
    Calculate real-time metrics from recent events.

    Args:
        pipeline_id: Pipeline identifier

    Returns:
        Metrics dictionary
    """
    # Query recent events from DynamoDB or Kinesis
    # Simplified implementation - in production, use time-series database

    run_table = dynamodb.Table('streamforge-runs')

    # Get recent runs (last 5 minutes)
    recent_runs = run_table.query(
        IndexName='pipeline-index',
        KeyConditionExpression='pipeline_id = :pid',
        ExpressionAttributeValues={':pid': pipeline_id},
        Limit=10,
        ScanIndexForward=False
    )

    if not recent_runs['Items']:
        return {
            'eventsPerSecond': 0,
            'anomalyRate': 0,
            'avgLatency': 0,
            'activeConnections': len(connections.get(pipeline_id, set()))
        }

    # Calculate metrics
    total_events = sum(r.get('events_processed', 0) for r in recent_runs['Items'])
    total_anomalies = sum(r.get('anomalies_detected', 0) for r in recent_runs['Items'])
    total_duration = sum(r.get('duration', 0) for r in recent_runs['Items'] if r.get('duration'))

    events_per_second = total_events / 60  # Over 1 minute window
    anomaly_rate = total_anomalies / total_events if total_events > 0 else 0
    avg_latency = (total_duration / len(recent_runs['Items'])) * 1000 if total_duration > 0 else 0

    return {
        'eventsPerSecond': round(events_per_second, 2),
        'anomalyRate': round(anomaly_rate, 4),
        'avgLatency': round(avg_latency, 2),
        'activeConnections': len(connections.get(pipeline_id, set())),
        'anomaliesPerSecond': round((total_anomalies / 60), 2)
    }


# Lambda function for periodic metrics broadcast (triggered by EventBridge every 1 second)
def metrics_broadcaster(event, context):
    """
    Broadcast real-time metrics to all connected clients.

    Triggered by EventBridge rule every 1 second.
    """
    endpoint_url = event.get('endpoint_url')

    if not endpoint_url:
        logger.error("Missing endpoint_url in event")
        return {'statusCode': 400, 'body': 'Missing endpoint_url'}

    # Broadcast metrics for each active pipeline
    for pipeline_id in connections.keys():
        if not connections[pipeline_id]:
            continue

        try:
            metrics = calculate_realtime_metrics(pipeline_id)
            broadcast_metrics(pipeline_id, metrics, endpoint_url)
        except Exception as e:
            logger.error(f"Error broadcasting metrics for pipeline {pipeline_id}: {e}")

    return {'statusCode': 200, 'body': f'Broadcasted to {len(connections)} pipelines'}


# Example usage: Trigger from Kinesis stream
def kinesis_event_forwarder(event, context):
    """
    Forward Kinesis events to WebSocket clients in real-time.

    Triggered by Kinesis stream whenever new events arrive.
    """
    endpoint_url = context.client_context.get('endpoint_url') if context.client_context else None

    if not endpoint_url:
        logger.error("Missing endpoint_url in context")
        return

    for record in event['Records']:
        # Decode Kinesis data
        payload = json.loads(record['kinesis']['data'])

        pipeline_id = payload.get('pipeline_id')
        if not pipeline_id:
            continue

        # Broadcast event to connected clients
        broadcast_event(pipeline_id, payload, endpoint_url)

    return {'statusCode': 200, 'body': f'Forwarded {len(event["Records"])} events'}
