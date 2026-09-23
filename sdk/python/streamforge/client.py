import json
import time
import os
from typing import Any, Optional
from pathlib import Path

import requests


class StreamForgeError(Exception):
    def __init__(self, message: str, status_code: int = 0, response: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}


class StreamForge:
    def __init__(
        self,
        api_url: str | None = None,
        analytics_url: str | None = None,
        api_key: str | None = None,
        org_id: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.api_url = (api_url or os.environ.get('STREAMFORGE_API_URL', '')).rstrip('/')
        self.analytics_url = (analytics_url or os.environ.get('STREAMFORGE_ANALYTICS_URL', self.api_url)).rstrip('/')
        self.api_key = api_key or os.environ.get('STREAMFORGE_API_KEY')
        self.org_id = org_id or os.environ.get('STREAMFORGE_ORG_ID', 'default')
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update({
            'Content-Type': 'application/json',
            'X-Org-Id': self.org_id,
        })
        if self.api_key:
            self._session.headers['X-Api-Key'] = self.api_key

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._session.close()

    def _request(self, method: str, url: str, **kwargs) -> dict:
        kwargs.setdefault('timeout', self.timeout)
        last_error = None

        for attempt in range(self.max_retries):
            try:
                resp = self._session.request(method, url, **kwargs)
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    time.sleep(wait)
                    continue
                data = resp.json()
                if resp.status_code >= 400:
                    raise StreamForgeError(
                        data.get('error', f'HTTP {resp.status_code}'),
                        status_code=resp.status_code,
                        response=data,
                    )
                return data
            except requests.exceptions.ConnectionError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
            except StreamForgeError:
                raise

        raise StreamForgeError(f'Failed after {self.max_retries} retries: {last_error}')

    def health(self) -> dict:
        return self._request('GET', f'{self.api_url}/health')

    def ingest(self, pipeline_id: str, events: list[dict[str, Any]]) -> dict:
        return self._request('POST', f'{self.api_url}/ingest', json={
            'pipeline': pipeline_id,
            'events': events,
        })

    def ingest_batch(self, pipeline_id: str, events: list[dict[str, Any]], batch_size: int = 500) -> list[dict]:
        results = []
        for i in range(0, len(events), batch_size):
            batch = events[i:i + batch_size]
            result = self.ingest(pipeline_id, batch)
            results.append(result)
        return results

    def create_pipeline(self, config: dict[str, Any]) -> dict:
        return self._request('POST', f'{self.api_url}/pipelines', json=config)

    def list_pipelines(self) -> dict:
        return self._request('GET', f'{self.api_url}/pipelines')

    def get_pipeline(self, pipeline_id: str) -> dict:
        return self._request('GET', f'{self.api_url}/pipelines/{pipeline_id}')

    def get_runs(self, pipeline_id: str) -> dict:
        return self._request('GET', f'{self.api_url}/pipelines/{pipeline_id}/runs')

    def upload_file(self, pipeline_id: str, filepath: str) -> dict:
        path = Path(filepath)
        content_type = 'text/csv' if path.suffix == '.csv' else 'application/json'

        presigned = self._request('POST', f'{self.api_url}/upload', json={
            'pipeline': pipeline_id,
            'filename': path.name,
            'content_type': content_type,
        })

        with open(filepath, 'rb') as f:
            requests.put(
                presigned['upload_url'],
                data=f.read(),
                headers={'Content-Type': content_type},
                timeout=300,
            )

        return presigned

    def query(self, sql: str, poll_interval: float = 1.0, max_wait: int = 60) -> dict:
        result = self._request('POST', f'{self.analytics_url}/query', json={'sql': sql})

        if result.get('status') == 'completed':
            return result

        query_id = result.get('query_id')
        if not query_id:
            return result

        start = time.time()
        while time.time() - start < max_wait:
            time.sleep(poll_interval)
            result = self._request('GET', f'{self.analytics_url}/query/{query_id}')
            if result.get('status') in ('completed', 'failed'):
                return result

        raise StreamForgeError(f'Query {query_id} timed out after {max_wait}s')

    def get_stats(self) -> dict:
        return self._request('GET', f'{self.analytics_url}/stats')

    def get_anomalies(self, pipeline_id: str | None = None) -> dict:
        params = f'?pipeline_id={pipeline_id}' if pipeline_id else ''
        return self._request('GET', f'{self.analytics_url}/anomalies{params}')

    def list_templates(self) -> dict:
        """List all available pipeline templates."""
        return self._request('GET', f'{self.api_url}/templates')

    def get_template(self, template_id: str) -> dict:
        """Get a specific template with variables and sample events."""
        return self._request('GET', f'{self.api_url}/templates/{template_id}')

    def create_from_template(self, template_id: str, variables: dict[str, Any] | None = None) -> dict:
        """
        Create a pipeline from a template with variable substitution.

        Args:
            template_id: Template ID (e.g., 'ecommerce', 'iot-sensors')
            variables: Template variables (e.g., {'pipeline_name': 'my-pipeline', 'anomaly_threshold': '0.05'})

        Returns:
            dict: Created pipeline details

        Example:
            >>> sf = StreamForge('https://api.streamforge.com')
            >>> sf.create_from_template('ecommerce', {
            ...     'pipeline_name': 'my-ecommerce',
            ...     'anomaly_threshold': '0.05',
            ...     'aggregation_window': '1h'
            ... })
        """
        return self._request('POST', f'{self.api_url}/pipelines/from-template', json={
            'template_id': template_id,
            'variables': variables or {},
        })
