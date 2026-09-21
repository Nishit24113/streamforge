# StreamForge Python SDK

Integrate any Python project with StreamForge in 2 lines.

## Install

```bash
pip install streamforge
```

## Quick Start

```python
from streamforge import StreamForge

sf = StreamForge("https://your-api-url.com")
sf.ingest("my-pipeline", [{"user": "john", "action": "purchase", "amount": 99.99}])
```

## Decorator Integration

```python
from streamforge.decorators import streamforge_track

@streamforge_track("web-analytics")
def handle_request(request):
    return process(request)
```

## Environment Variables

- `STREAMFORGE_API_URL` — API endpoint
- `STREAMFORGE_ANALYTICS_URL` — Analytics endpoint (defaults to API URL)
- `STREAMFORGE_API_KEY` — API key for authentication
- `STREAMFORGE_ORG_ID` — Organization ID for multi-tenant isolation

## Multi-Tenant

```python
sf = StreamForge("https://api.example.com", org_id="my-org")
```
