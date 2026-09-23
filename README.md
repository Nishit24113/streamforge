# StreamForge

**Real-Time Serverless Data Pipeline Platform for AWS**

StreamForge is a production-grade, multi-tenant data engineering platform that ingests, transforms, and analyzes streaming data in real time. Built entirely on AWS serverless services, it provides configurable ETL pipelines, a columnar data lake, serverless SQL analytics, and a live monitoring dashboard. Integrate with any project in 1-2 commands.

---

## Why StreamForge?

Traditional data pipeline tools (Airflow, Spark, Kafka) require cluster management, scaling headaches, and high costs. StreamForge delivers the same capabilities — streaming ingestion, transformation, analytics — without a single server to manage.

| Feature | StreamForge | Traditional Stack |
|---------|-------------|-------------------|
| Infrastructure | Zero servers | Kafka + Spark clusters |
| Scaling | Automatic | Manual tuning |
| Cost (dev/test) | $0-5/month | $200-500/month |
| Setup time | 15 minutes | Days to weeks |
| Maintenance | None | Ongoing |
| Integration | 1-2 commands | Custom integration |
| Multi-tenant | Built-in | Custom implementation |

---

## Architecture

```
Data Sources                    Ingestion              Processing
┌──────────┐                 ┌─────────────┐      ┌──────────────────┐
│ Webhooks │─────┐           │             │      │  Step Functions   │
├──────────┤     │           │ API Gateway │─────▶│  Pipeline Engine  │
│ REST API │─────┼──────────▶│  + Lambda   │      │                  │
├──────────┤     │           │             │      │  ┌────────────┐  │
│ CSV/JSON │─────┘           └─────────────┘      │  │ Validate   │  │
│  Upload  │                        │              │  │ Transform  │  │
└──────────┘                        │              │  │ ML Detect  │  │
                                    ▼              │  │ Aggregate  │  │
                             ┌─────────────┐      │  └────────────┘  │
                             │  Kinesis     │      │                  │
                             │  Data Stream │─────▶│                  │
                             └─────────────┘      └────────┬─────────┘
                                                           │
                    Storage                                │
         ┌──────────────────────────┐                      │
         │   S3 Data Lake           │◀─────────────────────┘
         │   (Apache Parquet)       │
         │                          │         Analytics
         │  raw/    → raw events    │      ┌──────────────┐
         │  clean/  → transformed   │─────▶│   Athena     │
         │  agg/    → aggregated    │      │  (SQL Query) │
         └──────────────────────────┘      └──────┬───────┘
                                                   │
         ┌──────────────────────────┐              │
         │   DynamoDB               │              ▼
         │  - Pipeline configs      │      ┌──────────────┐
         │  - Run history           │      │  React       │
         │  - Anomaly alerts        │      │  Dashboard   │
         └──────────────────────────┘      └──────────────┘
```

---

## Quick Integration (1-2 Commands)

### Option 1: Use a Template (Fastest!)

```bash
# Install CLI
npm install -g streamforge-cli

# Create pipeline from template
streamforge create from-template ecommerce --name my-shop-events

# Start sending events
streamforge ingest my-shop-events events.json
```

### Option 2: Python SDK with Template

```bash
pip install streamforge
```

```python
from streamforge import StreamForge

sf = StreamForge("https://your-api-url.com")

# Create pipeline from template
sf.create_from_template('ecommerce', {
    'pipeline_name': 'my-shop-events',
    'anomaly_threshold': '0.05'
})

# Start ingesting
sf.ingest("my-shop-events", [{"user_id": "john", "event_type": "purchase", "amount": 99.99}])
```

### Option 3: Node.js SDK

```bash
npm install streamforge
```

```typescript
import { StreamForge } from 'streamforge';

const sf = new StreamForge({ apiUrl: 'https://your-api-url.com' });
await sf.ingest('my-pipeline', [{ user: 'john', action: 'purchase', amount: 99.99 }]);
```

### Option 4: Express Middleware (Zero-Code Integration)

```typescript
import { streamforgeMiddleware } from 'streamforge/middleware';

app.use(streamforgeMiddleware({
  pipelineId: 'web-analytics',
  apiUrl: 'https://your-api-url.com',
}));
```

### Option 5: Python Decorator

```python
from streamforge.decorators import streamforge_track

@streamforge_track("web-analytics")
def handle_request(request):
    return process(request)
```

---

## Features

### Pipeline Templates (NEW! 🚀)
- **5 Pre-built Templates** — E-commerce, IoT sensors, web analytics, application logs, financial transactions
- **Variable Substitution** — Customize thresholds, windows, field names without writing JSON
- **Instant Setup** — Create production-ready pipelines in one command
- **SDK & CLI Support** — `sf.create_from_template('ecommerce', {'pipeline_name': 'my-shop'})`
- See [TEMPLATES.md](TEMPLATES.md) for full documentation

### Monitoring & Alerting
- **CloudWatch Dashboard** — Real-time metrics for ingestion, processing, anomalies
- **Custom Metrics** — Events processed, anomalies detected, anomaly rate per pipeline
- **Automated Alerts** — SNS notifications for high failure rate, anomaly spikes, throttling, dead pipelines
- **4 Production Alarms** — Pipeline failures, data quality issues, Kinesis throttling, no-data detection
- See [MONITORING.md](MONITORING.md) for full documentation

### Data Ingestion
- **REST API** — Send JSON events via HTTP POST (batch up to 500)
- **Webhook Receiver** — GitHub, Stripe, and custom webhook parsers with HMAC verification
- **File Upload** — Upload CSV/JSON via presigned URLs, auto-processed by S3 trigger
- **Kinesis Streaming** — On-demand scaling, 24h retention, DLQ fallback

### Pipeline Engine (Step Functions)
- **12 Built-in Transforms** — rename, cast, flatten, hash, filter, map_values, extract, add_field, remove_field, lowercase, uppercase, default
- **Schema Validation** — Type checking, null rejection, range bounds
- **4 Anomaly Detection Algorithms** — Isolation Forest, Z-Score, IQR, MAD
- **9 Aggregation Metrics** — sum, avg, min, max, count, count_distinct, stddev, p50, p95, p99
- **Time-Window Aggregations** — 1m, 5m, 15m, 1h, 6h, 1d windows with group-by

### Data Lake (S3 + Parquet)
- **Three-Zone Architecture** — Raw → Clean → Aggregated
- **Date Partitioned** — year/month/day for efficient Athena queries
- **Lifecycle Management** — Infrequent Access at 30d, Glacier at 90d
- **Snappy Compression** — ~90% size reduction

### Analytics (Athena)
- **Serverless SQL** — Query petabytes, pay $5/TB scanned
- **1GB Scan Limit** — Cost guardrails per query via workgroup
- **SQL Injection Protection** — Only SELECT/WITH/SHOW/DESCRIBE allowed
- **Pre-built Named Queries** — Event counts, anomaly summary, hourly throughput

### Multi-Tenant SaaS
- **Organization Isolation** — X-Org-Id header for tenant separation
- **Per-Tenant Pipelines** — Pipeline listing filtered by org
- **Tenant-Scoped Storage** — S3 paths include org context
- **SDK Support** — `org_id` parameter on all SDK clients

### Dashboard (React 19)
- **Live Overview** — 6 stat cards, 4 real-time charts
- **Pipeline Monitor** — Expandable cards with run history, test data sender
- **Anomaly Timeline** — Scatter chart with severity filtering
- **SQL Query Editor** — Full SQL with auto-polling and CSV export
- **Data Explorer** — Three-zone S3 browser with storage visualization

---

## Tech Stack

### Backend
| Technology | Purpose |
|-----------|---------|
| **Python 3.12** | Lambda functions |
| **AWS Lambda** (ARM64/Graviton) | Serverless compute |
| **API Gateway** | REST API with CORS |
| **Kinesis Data Streams** | Real-time event streaming (on-demand) |
| **Step Functions** | Pipeline orchestration |
| **S3** | Three-zone data lake |
| **Apache Parquet** | Columnar storage with Snappy |
| **Athena v3** | Serverless SQL analytics |
| **Glue Data Catalog** | Schema registry |
| **DynamoDB** | Metadata, run history, alerts (with TTL) |
| **SQS** | Dead letter queue |

### Frontend
| Technology | Purpose |
|-----------|---------|
| **React 19** | UI framework |
| **Vite 6** | Build tool |
| **Tailwind CSS 3** | Glass-morphism design system |
| **Framer Motion** | Smooth animations |
| **Recharts** | Area, Bar, Line, Scatter, Pie charts |
| **React Query** | Server state with auto-refresh |

### Infrastructure
| Technology | Purpose |
|-----------|---------|
| **AWS CDK 2.x** | Infrastructure as Code (TypeScript) |
| **4 CloudFormation Stacks** | Storage, Ingestion, Processing, Analytics |

### SDKs & CLI
| Component | Install |
|-----------|---------|
| **Python SDK** | `pip install streamforge` |
| **Node.js SDK** | `npm install streamforge` |
| **CLI** | `npx streamforge-cli` |

---

## Quick Start

### Prerequisites
- AWS account with CLI configured
- Node.js 18+ and Python 3.10+

### Deploy to AWS

```bash
git clone https://github.com/Nishit24113/streamforge.git
cd streamforge
./deploy.sh --profile YOUR_AWS_PROFILE --region us-west-2
```

### Local Development (No AWS)

```bash
cd dashboard && npm install && npm run dev
# Dashboard at http://localhost:5173 with mock data
```

### CLI Quick Start

```bash
streamforge init                           # Interactive setup
streamforge connect https://your-api.com   # Connect to deployed API
streamforge status                         # Check health + stats
streamforge ingest my-pipeline data.json   # Send events from file
streamforge deploy --profile sandbox2025   # Deploy infrastructure
```

---

## Project Structure

```
streamforge/
├── infrastructure/          # AWS CDK (TypeScript)
│   ├── lib/
│   │   ├── storage-stack.ts       # S3, DynamoDB, Glue
│   │   ├── ingestion-stack.ts     # API Gateway, Kinesis, Lambda
│   │   ├── processing-stack.ts    # Step Functions, Transform Lambdas
│   │   └── analytics-stack.ts     # Athena, workgroups, queries
│   └── bin/streamforge.ts
│
├── services/                # Lambda functions (Python 3.12)
│   ├── ingestion/
│   │   ├── api-handler/           # REST API (ingest, pipelines, upload)
│   │   ├── webhook-handler/       # GitHub/Stripe/generic webhooks
│   │   └── file-processor/        # CSV/JSON S3 trigger
│   ├── processing/
│   │   ├── stream-processor/      # Kinesis → Step Functions
│   │   ├── validator/             # Schema validation
│   │   ├── transformer/           # 12 transform operations
│   │   ├── anomaly-detector/      # 4 ML algorithms
│   │   └── aggregator/            # Time-window aggregations
│   ├── analytics/
│   │   └── query-runner/          # Athena SQL executor
│   └── shared/
│       ├── config.py              # Connection pooling
│       └── parquet_writer.py      # Parquet serialization
│
├── dashboard/               # React 19 frontend
│   └── src/
│       ├── components/
│       │   ├── Overview.jsx       # Stats + 4 charts
│       │   ├── PipelineMonitor.jsx # Pipeline cards + test data
│       │   ├── AnomalyTimeline.jsx # Scatter chart + list
│       │   ├── QueryEditor.jsx    # SQL editor + results
│       │   └── DataExplorer.jsx   # S3 browser + storage chart
│       ├── utils/api.js           # API client + mock data
│       └── App.jsx                # Layout + navigation
│
├── sdk/                     # Integration SDKs
│   ├── python/                    # pip install streamforge
│   │   └── streamforge/
│   │       ├── client.py          # StreamForge client class
│   │       └── decorators.py      # @streamforge_event, @streamforge_track
│   └── node/                      # npm install streamforge
│       └── src/
│           ├── index.ts           # StreamForge client class
│           └── middleware.ts       # Express/Fastify middleware
│
├── cli/                     # streamforge-cli
│   ├── bin/streamforge.js         # CLI entry point
│   └── src/commands/              # init, connect, ingest, status, deploy
│
├── pipelines/               # Demo pipeline configs
│   ├── demo-ecommerce.json        # E-commerce with anomaly detection
│   ├── demo-iot-sensors.json      # IoT sensor readings
│   └── demo-web-analytics.json    # Web analytics with PII hashing
│
├── data/samples/            # Sample data for testing
├── deploy.sh                # One-click deployment script
└── LICENSE                  # MIT
```

---

## Pipeline Configuration

```json
{
  "name": "ecommerce-events",
  "steps": [
    {
      "type": "validate",
      "schema": { "user_id": "string", "amount": "number" },
      "reject_nulls": ["user_id"]
    },
    {
      "type": "transform",
      "operations": [
        { "op": "rename", "from": "user_id", "to": "customer_id" },
        { "op": "add_field", "name": "processed_at", "value": "$NOW" },
        { "op": "hash", "field": "email", "algorithm": "sha256" }
      ]
    },
    {
      "type": "detect_anomalies",
      "field": "amount",
      "method": "isolation_forest",
      "contamination": 0.05
    },
    {
      "type": "aggregate",
      "window": "1h",
      "group_by": ["action"],
      "metrics": [
        { "field": "amount", "agg": "sum", "alias": "total_revenue" },
        { "field": "amount", "agg": "p95", "alias": "p95_order_value" },
        { "field": "customer_id", "agg": "count_distinct", "alias": "unique_customers" }
      ]
    }
  ],
  "detect_anomalies": true,
  "aggregate": true
}
```

---

## Cost Analysis

| Service | Free Tier | Expected Usage | Monthly Cost |
|---------|-----------|----------------|-------------|
| Lambda | 1M requests | 500K | $0 |
| API Gateway | 1M requests | 500K | $0 |
| S3 | 5GB | 2GB | $0 |
| DynamoDB | 25GB | 5GB | $0 |
| Athena | — | 10GB scanned | $0.05 |
| Kinesis | — | On-demand | ~$3 |
| Step Functions | 4000 transitions | 3000 | $0 |
| **Total** | | | **~$3-5/month** |

---

## License

MIT License — See [LICENSE](LICENSE)

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
