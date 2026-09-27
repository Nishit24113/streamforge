"""
BigQuery integration for streaming StreamForge events.

Enables real-time data warehouse analytics by streaming processed events
directly to BigQuery tables.
"""

import json
import os
from datetime import datetime


class BigQueryExporter:
    """Stream events to BigQuery in real-time."""

    def __init__(self, project_id, dataset_id, table_id):
        """
        Initialize BigQuery exporter.

        Args:
            project_id: GCP project ID
            dataset_id: BigQuery dataset name
            table_id: BigQuery table name
        """
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.table_id = table_id
        self.client = None

    def _get_client(self):
        """Lazy initialization of BigQuery client."""
        if self.client is None:
            try:
                from google.cloud import bigquery
                self.client = bigquery.Client(project=self.project_id)
            except ImportError:
                raise ImportError('google-cloud-bigquery not installed. Run: pip install google-cloud-bigquery')
        return self.client

    def stream_events(self, events):
        """
        Stream events to BigQuery.

        Args:
            events: List of event dictionaries

        Returns:
            dict: {
                'success': True/False,
                'rows_streamed': int,
                'errors': []
            }
        """
        client = self._get_client()
        table_ref = f'{self.project_id}.{self.dataset_id}.{self.table_id}'

        # Transform events to BigQuery format
        rows = [self._transform_event(evt) for evt in events]

        # Stream insert
        errors = client.insert_rows_json(table_ref, rows)

        return {
            'success': len(errors) == 0,
            'rows_streamed': len(rows) if len(errors) == 0 else 0,
            'errors': errors
        }

    def _transform_event(self, event):
        """
        Transform StreamForge event to BigQuery row.

        BigQuery schema:
        - event_id: STRING
        - pipeline_id: STRING
        - timestamp: TIMESTAMP
        - event_type: STRING
        - source: STRING
        - is_anomaly: BOOLEAN
        - anomaly_score: FLOAT
        - payload: JSON (STRING)
        """
        payload = event.get('payload', {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}

        # Convert timestamp (milliseconds) to BigQuery TIMESTAMP
        timestamp_ms = event.get('timestamp', int(datetime.utcnow().timestamp() * 1000))
        timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000).isoformat()

        return {
            'event_id': event.get('event_id', ''),
            'pipeline_id': event.get('pipeline_id', ''),
            'timestamp': timestamp_dt,
            'event_type': event.get('event_type', ''),
            'source': event.get('source', ''),
            'is_anomaly': event.get('is_anomaly', False),
            'anomaly_score': float(event.get('anomaly_score', 0)),
            'payload': json.dumps(payload)
        }

    def create_table_if_not_exists(self):
        """
        Create BigQuery table with StreamForge schema if it doesn't exist.

        Returns:
            bool: True if table was created or already exists
        """
        client = self._get_client()
        from google.cloud import bigquery

        table_ref = f'{self.project_id}.{self.dataset_id}.{self.table_id}'

        schema = [
            bigquery.SchemaField('event_id', 'STRING', mode='REQUIRED'),
            bigquery.SchemaField('pipeline_id', 'STRING', mode='REQUIRED'),
            bigquery.SchemaField('timestamp', 'TIMESTAMP', mode='REQUIRED'),
            bigquery.SchemaField('event_type', 'STRING'),
            bigquery.SchemaField('source', 'STRING'),
            bigquery.SchemaField('is_anomaly', 'BOOLEAN'),
            bigquery.SchemaField('anomaly_score', 'FLOAT'),
            bigquery.SchemaField('payload', 'JSON'),
        ]

        table = bigquery.Table(table_ref, schema=schema)

        # Partition by timestamp for query performance
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field='timestamp'
        )

        # Cluster by pipeline_id for filtering efficiency
        table.clustering_fields = ['pipeline_id', 'event_type']

        try:
            client.create_table(table)
            return True
        except Exception as e:
            if 'Already Exists' in str(e):
                return True
            print(f'Error creating table: {e}')
            return False


class SnowflakeExporter:
    """Bulk export events to Snowflake data warehouse."""

    def __init__(self, account, user, password, warehouse, database, schema, table):
        """
        Initialize Snowflake exporter.

        Args:
            account: Snowflake account identifier
            user: Snowflake username
            password: Snowflake password
            warehouse: Snowflake warehouse name
            database: Snowflake database name
            schema: Snowflake schema name
            table: Snowflake table name
        """
        self.account = account
        self.user = user
        self.password = password
        self.warehouse = warehouse
        self.database = database
        self.schema = schema
        self.table = table
        self.connection = None

    def _get_connection(self):
        """Lazy initialization of Snowflake connection."""
        if self.connection is None:
            try:
                import snowflake.connector
                self.connection = snowflake.connector.connect(
                    user=self.user,
                    password=self.password,
                    account=self.account,
                    warehouse=self.warehouse,
                    database=self.database,
                    schema=self.schema
                )
            except ImportError:
                raise ImportError('snowflake-connector-python not installed. Run: pip install snowflake-connector-python')
        return self.connection

    def bulk_insert(self, events):
        """
        Bulk insert events to Snowflake.

        Args:
            events: List of event dictionaries

        Returns:
            dict: {
                'success': True/False,
                'rows_inserted': int,
                'error': str or None
            }
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Prepare insert statement
            insert_sql = f"""
            INSERT INTO {self.table}
            (event_id, pipeline_id, timestamp, event_type, source, is_anomaly, anomaly_score, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """

            # Transform events
            rows = [self._transform_event(evt) for evt in events]

            # Execute batch insert
            cursor.executemany(insert_sql, rows)
            conn.commit()

            return {
                'success': True,
                'rows_inserted': len(rows),
                'error': None
            }

        except Exception as e:
            conn.rollback()
            return {
                'success': False,
                'rows_inserted': 0,
                'error': str(e)
            }
        finally:
            cursor.close()

    def _transform_event(self, event):
        """Transform StreamForge event to Snowflake row tuple."""
        payload = event.get('payload', {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}

        # Convert timestamp
        timestamp_ms = event.get('timestamp', int(datetime.utcnow().timestamp() * 1000))
        timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000)

        return (
            event.get('event_id', ''),
            event.get('pipeline_id', ''),
            timestamp_dt,
            event.get('event_type', ''),
            event.get('source', ''),
            event.get('is_anomaly', False),
            float(event.get('anomaly_score', 0)),
            json.dumps(payload)
        )

    def create_table_if_not_exists(self):
        """
        Create Snowflake table with StreamForge schema if it doesn't exist.

        Returns:
            bool: True if table was created or already exists
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.table} (
            event_id VARCHAR(255) NOT NULL,
            pipeline_id VARCHAR(255) NOT NULL,
            timestamp TIMESTAMP_NTZ NOT NULL,
            event_type VARCHAR(255),
            source VARCHAR(255),
            is_anomaly BOOLEAN,
            anomaly_score FLOAT,
            payload VARIANT,
            PRIMARY KEY (event_id)
        )
        """

        try:
            cursor.execute(create_sql)
            conn.commit()
            return True
        except Exception as e:
            print(f'Error creating table: {e}')
            return False
        finally:
            cursor.close()

    def close(self):
        """Close Snowflake connection."""
        if self.connection:
            self.connection.close()
            self.connection = None


# Lambda handler for BigQuery/Snowflake exports
def export_to_warehouse(event, context):
    """
    Lambda handler for data warehouse exports.

    Args:
        event: {
            'warehouse': 'bigquery' or 'snowflake',
            'events': [...],
            'config': {
                'project_id': '...',  # BigQuery
                'dataset_id': '...',  # BigQuery
                'table_id': '...',    # BigQuery
                'account': '...',     # Snowflake
                'user': '...',        # Snowflake
                'password': '...',    # Snowflake
                'warehouse': '...',   # Snowflake
                'database': '...',    # Snowflake
                'schema': '...',      # Snowflake
                'table': '...'        # Snowflake
            }
        }
    """
    warehouse = event.get('warehouse')
    events = event.get('events', [])
    config = event.get('config', {})

    if not events:
        return {'statusCode': 400, 'error': 'No events provided'}

    if warehouse == 'bigquery':
        exporter = BigQueryExporter(
            project_id=config.get('project_id'),
            dataset_id=config.get('dataset_id'),
            table_id=config.get('table_id')
        )
        result = exporter.stream_events(events)

        return {
            'statusCode': 200 if result['success'] else 500,
            'warehouse': 'bigquery',
            **result
        }

    elif warehouse == 'snowflake':
        exporter = SnowflakeExporter(
            account=config.get('account'),
            user=config.get('user'),
            password=config.get('password'),
            warehouse=config.get('warehouse'),
            database=config.get('database'),
            schema=config.get('schema'),
            table=config.get('table')
        )

        result = exporter.bulk_insert(events)
        exporter.close()

        return {
            'statusCode': 200 if result['success'] else 500,
            'warehouse': 'snowflake',
            **result
        }

    else:
        return {'statusCode': 400, 'error': 'Invalid warehouse. Use "bigquery" or "snowflake"'}
