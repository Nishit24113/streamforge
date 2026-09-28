# GraphQL API

Modern GraphQL API for StreamForge as an alternative to REST with type-safe queries, real-time subscriptions, and efficient data loading.

---

## Overview

StreamForge GraphQL API provides:
- **Type-Safe Queries** - Schema-driven API with automatic validation
- **Real-Time Subscriptions** - WebSocket-based live event streams
- **Efficient Data Loading** - No N+1 queries, single round-trip for nested data
- **Introspection** - Auto-generated documentation via GraphQL Playground
- **Field-Level Permissions** - Fine-grained access control

**Endpoint:** `https://api.streamforge.com/graphql`

---

## Quick Start

### GraphQL Playground

Access interactive API explorer at: `https://api.streamforge.com/graphql`

**Features:**
- Auto-complete queries
- Explore schema docs
- Test queries/mutations
- View real-time subscriptions

---

### Python Client

```python
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

# Create client
transport = RequestsHTTPTransport(url='https://api.streamforge.com/graphql')
client = Client(transport=transport, fetch_schema_from_transport=True)

# Query pipeline
query = gql('''
    query GetPipeline($id: ID!) {
        pipeline(id: $id) {
            id
            name
            stats {
                totalRuns
                anomalyRate
            }
            runs(limit: 5) {
                id
                status
                eventsProcessed
            }
        }
    }
''')

result = client.execute(query, variable_values={'id': 'pipeline-123'})
print(result)
```

---

### JavaScript Client

```javascript
import { GraphQLClient, gql } from 'graphql-request';

const client = new GraphQLClient('https://api.streamforge.com/graphql');

const query = gql`
  query GetPipelines {
    pipelines(limit: 10) {
      id
      name
      createdAt
      stats {
        totalEvents
        anomalyRate
      }
    }
  }
`;

const data = await client.request(query);
console.log(data.pipelines);
```

---

### cURL

```bash
curl -X POST https://api.streamforge.com/graphql \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query { pipelines(limit: 5) { id name } }"
  }'
```

---

## Queries

### Get Pipeline

```graphql
query GetPipeline($id: ID!) {
  pipeline(id: $id) {
    id
    name
    orgId
    detectAnomalies
    aggregate
    createdAt
    
    stats {
      totalRuns
      totalEvents
      totalAnomalies
      avgEventsPerRun
      anomalyRate
      successRate
    }
    
    runs(limit: 5) {
      id
      status
      eventsProcessed
      anomaliesDetected
      duration
      startTime
      endTime
    }
  }
}
```

**Variables:**
```json
{
  "id": "pipeline-123"
}
```

---

### List Pipelines

```graphql
query ListPipelines($limit: Int, $filter: PipelineFilter) {
  pipelines(limit: $limit, filter: $filter) {
    edges {
      node {
        id
        name
        orgId
        createdAt
      }
      cursor
    }
    pageInfo {
      hasNextPage
      endCursor
    }
    totalCount
  }
}
```

**Variables:**
```json
{
  "limit": 20,
  "filter": {
    "orgId": "my-org",
    "detectAnomalies": true
  }
}
```

---

### Query Events

```graphql
query GetEvents($pipelineId: ID!, $dateFrom: String, $dateTo: String, $limit: Int) {
  events(
    pipelineId: $pipelineId
    dateFrom: $dateFrom
    dateTo: $dateTo
    limit: $limit
  ) {
    id
    timestamp
    eventType
    source
    payload
    isAnomaly
    anomalyScore
  }
}
```

**Variables:**
```json
{
  "pipelineId": "pipeline-123",
  "dateFrom": "2026-09-01",
  "dateTo": "2026-09-28",
  "limit": 100
}
```

---

### Get Statistics

```graphql
query GetStats($pipelineId: ID) {
  stats(pipelineId: $pipelineId) {
    totalPipelines
    totalRuns
    totalEvents
    totalAnomalies
    avgEventsPerRun
    anomalyRate
  }
}
```

---

## Mutations

### Create Pipeline

```graphql
mutation CreatePipeline($input: CreatePipelineInput!) {
  createPipeline(input: $input) {
    pipeline {
      id
      name
      orgId
      createdAt
    }
    errors {
      message
      field
    }
  }
}
```

**Variables:**
```json
{
  "input": {
    "name": "ecommerce-events",
    "orgId": "my-org",
    "detectAnomalies": true,
    "aggregate": true
  }
}
```

---

### Ingest Events

```graphql
mutation IngestEvents($pipelineId: ID!, $events: [EventInput!]!) {
  ingestEvents(pipelineId: $pipelineId, events: $events) {
    eventsIngested
    run {
      id
      status
    }
    errors {
      message
    }
  }
}
```

**Variables:**
```json
{
  "pipelineId": "pipeline-123",
  "events": [
    {
      "eventType": "purchase",
      "source": "api",
      "payload": {
        "user_id": "user-456",
        "amount": 99.99,
        "product_id": "prod-789"
      }
    }
  ]
}
```

---

### Create from Template

```graphql
mutation CreateFromTemplate($templateId: ID!, $variables: JSON) {
  createFromTemplate(templateId: $templateId, variables: $variables) {
    pipeline {
      id
      name
      createdAt
    }
    errors {
      message
    }
  }
}
```

**Variables:**
```json
{
  "templateId": "ecommerce",
  "variables": {
    "pipeline_name": "my-ecommerce",
    "anomaly_threshold": "0.05"
  }
}
```

---

## Subscriptions (WebSocket)

### Real-Time Event Stream

```graphql
subscription EventStream($pipelineId: ID!) {
  eventStream(pipelineId: $pipelineId) {
    id
    timestamp
    eventType
    payload
    isAnomaly
  }
}
```

**Python Client (WebSocket):**
```python
from gql import gql, Client
from gql.transport.websockets import WebsocketsTransport

transport = WebsocketsTransport(url='wss://api.streamforge.com/graphql')
client = Client(transport=transport, fetch_schema_from_transport=True)

subscription = gql('''
    subscription EventStream($pipelineId: ID!) {
        eventStream(pipelineId: $pipelineId) {
            id
            timestamp
            eventType
            payload
            isAnomaly
        }
    }
''')

async for result in client.subscribe(subscription, variable_values={'pipelineId': 'pipeline-123'}):
    print(result)
```

---

### Anomaly Alerts

```graphql
subscription AnomalyDetected($pipelineId: ID) {
  anomalyDetected(pipelineId: $pipelineId) {
    id
    field
    value
    expectedRange
    severity
    method
    timestamp
  }
}
```

---

### Run Status Updates

```graphql
subscription RunStatus($pipelineId: ID!) {
  runStatusChanged(pipelineId: $pipelineId) {
    id
    status
    eventsProcessed
    anomaliesDetected
    duration
  }
}
```

---

## Schema Introspection

### Get Full Schema

```graphql
query IntrospectionQuery {
  __schema {
    queryType {
      name
    }
    mutationType {
      name
    }
    subscriptionType {
      name
    }
    types {
      name
      kind
      description
      fields {
        name
        type {
          name
          kind
        }
      }
    }
  }
}
```

---

### Get Type Details

```graphql
query GetTypeDetails($typeName: String!) {
  __type(name: $typeName) {
    name
    kind
    description
    fields {
      name
      description
      type {
        name
        kind
      }
      args {
        name
        type {
          name
        }
      }
    }
  }
}
```

**Variables:**
```json
{
  "typeName": "Pipeline"
}
```

---

## Advanced Queries

### Nested Data Loading (No N+1)

```graphql
query ComplexQuery {
  pipelines(limit: 10) {
    id
    name
    
    # Efficient: Single query loads all runs
    runs(limit: 5) {
      id
      status
      eventsProcessed
      
      # Efficient: DataLoader batches pipeline lookups
      pipeline {
        name
      }
    }
    
    # Computed field
    stats {
      anomalyRate
      successRate
    }
  }
}
```

**Performance:**
- REST: 1 + 10 + (10 × 5) = 61 requests
- GraphQL: 1 request (with DataLoader batching)

---

### Pagination (Cursor-Based)

```graphql
query PaginatedPipelines($first: Int, $after: String) {
  pipelines(first: $first, after: $after) {
    edges {
      node {
        id
        name
      }
      cursor
    }
    pageInfo {
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
    }
  }
}
```

**First Page:**
```json
{
  "first": 20
}
```

**Next Page:**
```json
{
  "first": 20,
  "after": "Y3Vyc29yOjIw"
}
```

---

### Aliasing (Multiple Queries in One Request)

```graphql
query MultipleQueries {
  prod: pipeline(id: "pipeline-123") {
    id
    name
    stats {
      anomalyRate
    }
  }
  
  staging: pipeline(id: "pipeline-456") {
    id
    name
    stats {
      anomalyRate
    }
  }
}
```

---

### Fragments (Reusable Fields)

```graphql
fragment PipelineStats on Pipeline {
  stats {
    totalRuns
    totalEvents
    anomalyRate
    successRate
  }
}

query CompareEnvironments {
  production: pipeline(id: "pipeline-123") {
    id
    name
    ...PipelineStats
  }
  
  staging: pipeline(id: "pipeline-456") {
    id
    name
    ...PipelineStats
  }
}
```

---

## Deployment

### AWS Lambda + API Gateway

```bash
cd services/graphql

# Install dependencies
pip install -r requirements.txt -t .

# Package for Lambda
zip -r graphql-api.zip .

# Deploy via AWS CLI
aws lambda create-function \
  --function-name streamforge-graphql \
  --runtime python3.12 \
  --handler handler.lambda_handler \
  --zip-file fileb://graphql-api.zip \
  --role arn:aws:iam::123456789012:role/StreamForge-GraphQL

# Create API Gateway endpoint
aws apigatewayv2 create-api \
  --name StreamForge-GraphQL \
  --protocol-type HTTP \
  --target arn:aws:lambda:us-east-1:123456789012:function:streamforge-graphql
```

---

### Local Development

```bash
cd services/graphql

# Install dependencies
pip install -r requirements.txt

# Run server
python handler.py

# Access GraphQL Playground
open http://localhost:8000/graphql
```

---

## Best Practices

### 1. Request Only Needed Fields

```graphql
# BAD: Over-fetching
query AllFields {
  pipelines {
    id
    name
    orgId
    steps
    detectAnomalies
    aggregate
    createdAt
    updatedAt
    runs { ... }
    stats { ... }
  }
}

# GOOD: Request only what you need
query MinimalFields {
  pipelines {
    id
    name
    stats {
      anomalyRate
    }
  }
}
```

---

### 2. Use Fragments for Repeated Fields

```graphql
# GOOD: Define fragment once, reuse everywhere
fragment PipelineSummary on Pipeline {
  id
  name
  createdAt
  stats {
    anomalyRate
  }
}

query MyPipelines {
  myPipelines: pipelines(filter: { orgId: "my-org" }) {
    ...PipelineSummary
  }
  
  sharedPipelines: pipelines(filter: { orgId: "shared" }) {
    ...PipelineSummary
  }
}
```

---

### 3. Use Variables (Not String Interpolation)

```graphql
# BAD: String interpolation (SQL injection risk)
query BadQuery {
  pipeline(id: "pipeline-${userInput}")
}

# GOOD: Variables with type validation
query GoodQuery($id: ID!) {
  pipeline(id: $id)
}
```

---

### 4. Paginate Large Result Sets

```graphql
# GOOD: Paginate instead of loading all
query PaginatedQuery($first: Int = 20, $after: String) {
  pipelines(first: $first, after: $after) {
    edges { node { id name } }
    pageInfo { hasNextPage endCursor }
  }
}
```

---

## Comparison: GraphQL vs REST

| Feature | GraphQL | REST |
|---------|---------|------|
| **Data Fetching** | Single request for nested data | Multiple requests (N+1 problem) |
| **Over/Under-fetching** | Request exactly what you need | Fixed response shape |
| **Versioning** | No versioning needed (schema evolution) | /v1, /v2, /v3 endpoints |
| **Type Safety** | Built-in (schema) | Manual (OpenAPI) |
| **Real-Time** | Native subscriptions (WebSocket) | Polling or separate WebSocket API |
| **Documentation** | Auto-generated (introspection) | Manual (Swagger/OpenAPI) |
| **Caching** | Complex (field-level) | Simple (HTTP caching) |

---

## Roadmap

- **Persisted Queries** - Pre-register queries for better security and performance
- **Batch Link** - Automatic batching of multiple queries into one HTTP request
- **DataLoader** - Eliminate N+1 queries with automatic batching and caching
- **Apollo Federation** - Federated GraphQL across microservices

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
