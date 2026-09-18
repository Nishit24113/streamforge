import os
import boto3

REGION = os.environ.get('AWS_REGION', 'us-west-2')
DATA_LAKE_BUCKET = os.environ.get('DATA_LAKE_BUCKET', 'streamforge-lake')
PIPELINE_TABLE = os.environ.get('PIPELINE_TABLE', 'streamforge-pipelines')
RUN_HISTORY_TABLE = os.environ.get('RUN_HISTORY_TABLE', 'streamforge-runs')
ALERTS_TABLE = os.environ.get('ALERTS_TABLE', 'streamforge-alerts')
KINESIS_STREAM = os.environ.get('KINESIS_STREAM', 'streamforge-events')

_sessions = {}

def get_resource(service_name: str):
    if service_name not in _sessions:
        _sessions[service_name] = boto3.resource(service_name, region_name=REGION)
    return _sessions[service_name]

def get_client(service_name: str):
    key = f'{service_name}_client'
    if key not in _sessions:
        _sessions[key] = boto3.client(service_name, region_name=REGION)
    return _sessions[key]
