# StreamForge

**Real-Time Serverless Data Pipeline Platform for AWS**

StreamForge is a production-grade data engineering platform that ingests, transforms, and analyzes streaming data in real time. Built entirely on AWS serverless services, it provides configurable ETL pipelines, a columnar data lake, serverless SQL analytics, and a live monitoring dashboard.

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

---

## Architecture

```
Data Sources                    Ingestion              Processing
┌──────────┐                 ┌─────────────┐      ┌──────────────────┐
│ Webhooks │─────┐           │             │      │  Step Functions   │
├──────────┤     │           │ API Gateway │─────▶│  Pipeline Engine  │
│ REST API │─────┼──────────▶│  + Lambda   │      │                  │
├──────────┤     │           │             │      │  ┌────────────┐  │
│ CSV/JSON │─────┘           └─────────────┘      │  │ Transform  │  │
│  Upload  │                        │              │  │ Validate   │  │
└──────────┘                        │              │  │ Enrich     │  │
                                    ▼              │  │ Aggregate  │  │
                             ┌─────────────┐      │  │ ML Detect  │  │
                             │  Kinesis     │      │  └────────────┘  │
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

## Features

### Data Ingestion
- **REST API** — Send JSON events via HTTP POST
- **Webhook Receiver** — Accept events from external services (GitHub, Stripe, etc.)
- **File Upload** — Upload CSV/JSON files for batch processing
- **Kinesis Streaming** — Real-time event stream with auto-scaling

### Pipeline Engine (Step Functions)
- **Configurable Pipelines** — Define transformation steps via JSON config
- **Built-in Transforms** — Filter, map, rename, type-cast, flatten, aggregate
- **Data Validation** — Schema validation with rejection handling
- **ML Enrichment** — Anomaly detection using Isolation Forest
- **Dead Letter Queue** — Failed records captured for debugging

### Data Lake (S3 + Parquet)
- **Columnar Storage** — Apache Parquet for 90% compression
- **Partitioned by Date** — Efficient time-range queries
- **Three-Zone Architecture** — Raw → Clean → Aggregated
- **Automatic Lifecycle** — Old data moves to Glacier after 90 days

### Analytics (Athena)
- **Serverless SQL** — Query petabytes without infrastructure
- **Pre-built Queries** — Common analytics out of the box
- **Cost-Effective** — Pay only $5 per TB scanned
- **Glue Catalog** — Automatic schema discovery

### Dashboard (React)
- **Live Pipeline Monitor** — Real-time execution status
- **Data Explorer** — Browse and query your data lake
- **Anomaly Alerts** — Visual anomaly detection timeline
- **Pipeline Builder** — Configure pipelines through UI
- **Cost Tracker** — Monitor AWS spend in real time

---

## Tech Stack

### Backend
| Technology | Purpose |
|-----------|---------|
| **Python 3.12** | Lambda functions, data processing |
| **AWS Lambda** (ARM64) | Serverless compute |
| **API Gateway** | REST API + WebSocket |
| **Kinesis Data Streams** | Real-time event streaming |
| **Step Functions** | Pipeline orchestration |
| **S3** | Data lake storage |
| **Apache Parquet** | Columnar data format |
| **Athena** | Serverless SQL queries |
| **Glue Data Catalog** | Schema management |
| **DynamoDB** | Metadata and config storage |
| **SQS** | Dead letter queue |
| **EventBridge** | Scheduled pipeline triggers |

### Frontend
| Technology | Purpose |
|-----------|---------|
| **React 19** | UI framework |
| **Vite 8** | Build tool |
| **Tailwind CSS 3** | Styling |
| **Framer Motion** | Animations |
| **Recharts** | Data visualization |
| **React Query** | Server state management |
| **Monaco Editor** | SQL query editor |

### Infrastructure
| Technology | Purpose |
|-----------|---------|
| **AWS CDK 2.x** | Infrastructure as Code (TypeScript) |
| **Python** | Lambda runtime |
| **Bash** | Deployment scripts |

---

## Quick Start

### Prerequisites
- AWS account with CLI configured
- Node.js 18+ and Python 3.10+
- Git

### Deploy (One Command)
```bash
git clone https://github.com/Nishit24113/streamforge.git
cd streamforge
./deploy.sh --profile YOUR_AWS_PROFILE --region us-west-2
```

### Local Development
```bash
# Start dashboard locally (no AWS needed)
cd dashboard
npm install
npm run dev
# Open http://localhost:5173
```

### Send Test Data
```bash
# Send event via API
curl -X POST https://YOUR-API.amazonaws.com/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline": "demo",
    "events": [
      {"user_id": "u123", "action": "purchase", "amount": 99.99, "timestamp": 1726617600}
    ]
  }'
```

---

## Project Structure

```
streamforge/
├── infrastructure/          # AWS CDK (TypeScript)
│   ├── lib/
│   │   ├── ingestion-stack.ts    # API Gateway, Kinesis, Lambda
│   │   ├── processing-stack.ts   # Step Functions, Transform Lambdas
│   │   ├── storage-stack.ts      # S3 data lake, DynamoDB, Glue
│   │   └── analytics-stack.ts    # Athena, workgroups, queries
│   ├── bin/streamforge.ts
│   ├── package.json
│   └── tsconfig.json
│
├── services/                # Lambda functions
│   ├── ingestion/
│   │   ├── api-handler/          # API Gateway event receiver
│   │   ├── webhook-handler/      # Webhook processor
│   │   └── file-processor/       # CSV/JSON file ingestion
│   ├── processing/
│   │   ├── transformer/          # Data transformation engine
│   │   ├── validator/            # Schema validation
│   │   ├── aggregator/           # Time-window aggregations
│   │   └── anomaly-detector/     # ML anomaly detection
│   ├── analytics/
│   │   ├── query-runner/         # Athena query executor
│   │   └── catalog-manager/      # Glue catalog management
│   └── shared/
│       ├── parquet_writer.py     # Parquet serialization
│       └── config.py             # Shared configuration
│
├── dashboard/               # React frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── PipelineMonitor.jsx
│   │   │   ├── DataExplorer.jsx
│   │   │   ├── QueryEditor.jsx
│   │   │   ├── AnomalyTimeline.jsx
│   │   │   └── PipelineBuilder.jsx
│   │   ├── utils/
│   │   └── App.jsx
│   └── package.json
│
├── pipelines/               # Pipeline definitions
│   ├── demo-ecommerce.json
│   ├── demo-iot-sensors.json
│   └── demo-web-analytics.json
│
├── deploy.sh                # One-click deployment
├── cleanup.sh               # AWS resource cleanup
└── README.md
```

---

## Pipeline Configuration

Define pipelines as JSON:

```json
{
  "name": "ecommerce-events",
  "description": "Process e-commerce purchase events",
  "source": {
    "type": "api",
    "format": "json"
  },
  "steps": [
    {
      "type": "validate",
      "schema": {
        "user_id": "string",
        "action": "string",
        "amount": "number",
        "timestamp": "number"
      }
    },
    {
      "type": "transform",
      "operations": [
        { "op": "rename", "from": "user_id", "to": "customer_id" },
        { "op": "add_field", "name": "processed_at", "value": "$NOW" },
        { "op": "cast", "field": "amount", "to": "decimal" }
      ]
    },
    {
      "type": "enrich",
      "lookup": "customer-metadata",
      "key": "customer_id"
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
        { "field": "amount", "agg": "sum" },
        { "field": "amount", "agg": "avg" },
        { "field": "customer_id", "agg": "count_distinct" }
      ]
    }
  ],
  "output": {
    "raw": "s3://streamforge-lake/raw/ecommerce/",
    "clean": "s3://streamforge-lake/clean/ecommerce/",
    "aggregated": "s3://streamforge-lake/agg/ecommerce/"
  }
}
```

---

## Cost Analysis

### With AWS Free Tier
| Service | Free Tier | Expected Usage | Monthly Cost |
|---------|-----------|----------------|-------------|
| Lambda | 1M requests | 500K | $0 |
| API Gateway | 1M requests | 500K | $0 |
| S3 | 5GB | 2GB | $0 |
| DynamoDB | 25GB | 5GB | $0 |
| Athena | — | 10GB scanned | $0.05 |
| Kinesis | — | Shard hours | ~$3 |
| Step Functions | 4000 transitions | 3000 | $0 |
| **Total** | | | **~$3-5/month** |

### vs Traditional Stack
| Solution | Monthly Cost |
|----------|-------------|
| **StreamForge** | $3-5 |
| Kafka + Spark (AWS EMR) | $300-800 |
| Databricks | $500-2000 |
| Snowflake + Fivetran | $400-1500 |

**Savings: 95-99%**

---

## Skills Demonstrated

- **Data Engineering** — ETL pipelines, streaming, batch processing
- **Data Lake Architecture** — S3 + Parquet + Glue + Athena
- **Stream Processing** — Kinesis real-time event handling
- **Pipeline Orchestration** — Step Functions state machines
- **ML in Production** — Anomaly detection in data pipelines
- **Serverless Architecture** — Zero infrastructure management
- **Infrastructure as Code** — AWS CDK (TypeScript)
- **Full-Stack Development** — React dashboard with SQL editor
- **Cost Optimization** — 95%+ savings vs traditional tools

---

## License

MIT License — See [LICENSE](LICENSE)

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
