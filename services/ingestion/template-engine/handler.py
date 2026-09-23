import json
import os
import re
import boto3

PIPELINE_TABLE = os.environ.get('PIPELINE_TABLE', 'streamforge-pipelines')
TEMPLATES_BUCKET = os.environ.get('TEMPLATES_BUCKET', '')

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
pipeline_table = dynamodb.Table(PIPELINE_TABLE)


def lambda_handler(event, context):
    """Template engine for creating pipelines from pre-built templates."""
    action = event.get('action', 'list')

    if action == 'list':
        return list_templates()
    elif action == 'get':
        template_id = event.get('template_id')
        return get_template(template_id)
    elif action == 'instantiate':
        return instantiate_template(event)
    else:
        return {'statusCode': 400, 'error': 'Invalid action'}


def list_templates():
    """List all available pipeline templates."""
    templates = [
        {
            'id': 'ecommerce',
            'name': 'E-Commerce Events',
            'description': 'Track purchases, cart actions, and detect fraudulent transactions',
            'category': 'retail',
            'use_cases': ['fraud detection', 'revenue tracking', 'customer analytics']
        },
        {
            'id': 'iot-sensors',
            'name': 'IoT Sensor Data',
            'description': 'Monitor sensor readings with anomaly detection for temperature, pressure, humidity',
            'category': 'industrial',
            'use_cases': ['predictive maintenance', 'quality control', 'environmental monitoring']
        },
        {
            'id': 'web-analytics',
            'name': 'Web Analytics',
            'description': 'Track page views, user sessions, and conversions with PII hashing',
            'category': 'marketing',
            'use_cases': ['conversion tracking', 'session analysis', 'GDPR compliance']
        },
        {
            'id': 'application-logs',
            'name': 'Application Logs',
            'description': 'Aggregate error rates, track exceptions, and monitor application health',
            'category': 'observability',
            'use_cases': ['error tracking', 'performance monitoring', 'alerting']
        },
        {
            'id': 'financial-transactions',
            'name': 'Financial Transactions',
            'description': 'Monitor payments and transfers with fraud detection and compliance tracking',
            'category': 'fintech',
            'use_cases': ['fraud detection', 'compliance reporting', 'transaction analytics']
        }
    ]

    return {
        'statusCode': 200,
        'templates': templates,
        'count': len(templates)
    }


def get_template(template_id):
    """Get a specific template with full configuration."""
    if not template_id:
        return {'statusCode': 400, 'error': 'template_id required'}

    # Load from embedded templates (in production, these could be in S3)
    template_path = f'/var/task/templates/{template_id}.json'

    try:
        with open(template_path, 'r') as f:
            template = json.load(f)

        return {
            'statusCode': 200,
            'template': template
        }
    except FileNotFoundError:
        return {
            'statusCode': 404,
            'error': f'Template {template_id} not found'
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'error': str(e)
        }


def instantiate_template(event):
    """
    Create a pipeline from a template with variable substitution.

    Args:
        event: {
            'template_id': 'ecommerce',
            'org_id': 'default',
            'variables': {
                'pipeline_name': 'my-ecommerce',
                'anomaly_threshold': '0.05',
                'aggregation_window': '1h'
            }
        }
    """
    template_id = event.get('template_id')
    org_id = event.get('org_id', 'default')
    variables = event.get('variables', {})

    if not template_id:
        return {'statusCode': 400, 'error': 'template_id required'}

    # Load template
    template_result = get_template(template_id)
    if template_result['statusCode'] != 200:
        return template_result

    template = template_result['template']

    # Apply defaults for missing variables
    for var_name, var_config in template.get('variables', {}).items():
        if var_name not in variables:
            if var_config.get('required'):
                return {
                    'statusCode': 400,
                    'error': f'Required variable {var_name} not provided'
                }
            variables[var_name] = var_config.get('default')

    # Substitute variables in config
    config_str = json.dumps(template['config'])
    for var_name, var_value in variables.items():
        placeholder = f'{{{{{var_name}}}}}'
        config_str = config_str.replace(placeholder, str(var_value))

    pipeline_config = json.loads(config_str)

    # Save pipeline to DynamoDB
    pipeline_id = pipeline_config['name']

    try:
        pipeline_table.put_item(Item={
            'pipeline_id': pipeline_id,
            'org_id': org_id,
            'config': json.dumps(pipeline_config),
            'template_id': template_id,
            'created_at': int(__import__('time').time()),
            'created_by': 'template-engine',
            'status': 'active'
        })

        return {
            'statusCode': 201,
            'pipeline_id': pipeline_id,
            'template_id': template_id,
            'config': pipeline_config,
            'message': f'Pipeline {pipeline_id} created from template {template_id}'
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'error': f'Failed to create pipeline: {str(e)}'
        }


def validate_variables(variables, template_variables):
    """Validate that provided variables match template requirements."""
    errors = []

    for var_name, var_config in template_variables.items():
        if var_config.get('required') and var_name not in variables:
            errors.append(f'Missing required variable: {var_name}')

    return errors
