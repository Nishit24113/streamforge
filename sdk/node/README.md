# StreamForge Node.js SDK

Node.js/TypeScript SDK for the StreamForge serverless real-time data pipeline platform.

## Install

```bash
npm install streamforge
```

Requires Node.js 18+ (uses native `fetch`).

## Quick Start

```typescript
import { StreamForge } from 'streamforge';

const sf = new StreamForge({ apiUrl: 'https://api.example.com' });
await sf.ingest('my-pipeline', [{ user: 'john', action: 'purchase', amount: 99.99 }]);
```

## Express Middleware (1 line)

```typescript
import { streamforgeMiddleware } from 'streamforge/middleware';

app.use(streamforgeMiddleware({ pipelineId: 'web-analytics', apiUrl: 'https://api.example.com' }));
```

## Configuration

```typescript
const sf = new StreamForge({
  apiUrl: 'https://api.example.com',
  analyticsUrl: 'https://analytics.example.com', // optional, defaults to apiUrl
  apiKey: 'sf_live_abc123',                       // optional
  orgId: 'org_456',                               // optional, sent as X-Org-Id header
});
```

## API

| Method | Description |
|---|---|
| `ingest(pipelineId, events)` | Send events to a pipeline |
| `ingestBatch(pipelineId, events, batchSize?)` | Auto-batch large event lists |
| `createPipeline(config)` | Create a new pipeline |
| `listPipelines()` | List all pipelines |
| `getPipeline(pipelineId)` | Get a single pipeline |
| `getRuns(pipelineId)` | Get run history |
| `uploadFile(pipelineId, filepath)` | Upload a file via presigned URL |
| `query(sql)` | Run SQL query (auto-polls for results) |
| `getStats()` | Get pipeline statistics |
| `getAnomalies(pipelineId?)` | Get anomaly timeline |
| `health()` | Health check |

## Error Handling

```typescript
import { StreamForgeError } from 'streamforge';

try {
  await sf.ingest('pipeline', events);
} catch (err) {
  if (err instanceof StreamForgeError) {
    console.error(err.statusCode, err.responseBody);
  }
}
```

## License

MIT
