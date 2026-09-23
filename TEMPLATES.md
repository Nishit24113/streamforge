# StreamForge Pipeline Templates

Get started in seconds with pre-built pipeline configurations for common use cases.

---

## Overview

Templates provide production-ready pipeline configurations with:
- **Pre-configured transforms** - Validation, PII hashing, type casting
- **Anomaly detection** - Fraud detection, sensor monitoring, error spikes
- **Aggregations** - Revenue metrics, device readings, log counts
- **Variable substitution** - Customize thresholds, windows, field names

---

## Available Templates

### 1. E-Commerce Events

**Use Cases:** Fraud detection, revenue tracking, customer analytics

**Variables:**
- `pipeline_name` (default: `ecommerce-events`) - Pipeline identifier
- `anomaly_threshold` (default: `0.05`) - Contamination rate for fraud detection (0.01-0.10)
- `aggregation_window` (default: `1h`) - Time window for revenue aggregation (1m, 5m, 15m, 1h)

**What it does:**
- Validates user_id, amount, timestamp
- Hashes email addresses (PII compliance)
- Detects fraudulent transactions using Isolation Forest
- Aggregates total revenue, p95 order value, unique customers per hour

**Sample event:**
```json
{
  "user_id": "user_12345",
  "email": "customer@example.com",
  "event_type": "purchase",
  "amount": 99.99,
  "currency": "USD",
  "product_id": "prod_abc",
  "timestamp": 1695000000000
}
```

---

### 2. IoT Sensor Data

**Use Cases:** Predictive maintenance, quality control, environmental monitoring

**Variables:**
- `pipeline_name` (default: `iot-sensor-monitoring`) - Pipeline identifier
- `sensor_field` (default: `temperature`) - Field to monitor (temperature, pressure, humidity, vibration)
- `zscore_threshold` (default: `2.5`) - Z-score threshold for anomaly detection (2.0-4.0)
- `aggregation_window` (default: `5m`) - Time window for sensor aggregation (1m, 5m, 15m)

**What it does:**
- Validates device_id, sensor_type, sensor readings
- Detects anomalous sensor readings using Z-Score
- Aggregates avg, min, max, stddev per device/sensor every 5 minutes

**Sample event:**
```json
{
  "device_id": "sensor_001",
  "sensor_type": "temperature",
  "temperature": 72.5,
  "unit": "fahrenheit",
  "location": "warehouse_a",
  "timestamp": 1695000000000
}
```

---

### 3. Web Analytics

**Use Cases:** Conversion tracking, session analysis, GDPR compliance

**Variables:**
- `pipeline_name` (default: `web-analytics`) - Pipeline identifier
- `pii_fields` (default: `email,ip_address`) - Comma-separated PII fields to hash
- `aggregation_window` (default: `1h`) - Time window for session aggregation (15m, 1h, 6h)

**What it does:**
- Validates user_id, page_url, event, timestamp
- Hashes email and IP address for GDPR compliance
- Extracts domain from page URL
- Aggregates unique visitors and total events per page/hour

**Sample event:**
```json
{
  "user_id": "user_67890",
  "email": "visitor@example.com",
  "ip_address": "192.168.1.1",
  "page_url": "https://example.com/products/shoes",
  "event": "page_view",
  "referrer": "https://google.com",
  "timestamp": 1695000000000
}
```

---

### 4. Application Logs

**Use Cases:** Error tracking, performance monitoring, alerting

**Variables:**
- `pipeline_name` (default: `app-logs-monitoring`) - Pipeline identifier
- `error_threshold` (default: `0.05`) - Contamination rate for error spikes (0.01-0.10)
- `aggregation_window` (default: `15m`) - Time window for error aggregation (5m, 15m, 1h)

**What it does:**
- Validates service_name, log_level, message
- Filters to WARN/ERROR/FATAL logs only
- Detects error spikes using Isolation Forest
- Aggregates log counts, avg/p95/p99 response time per service

**Sample event:**
```json
{
  "service_name": "auth-service",
  "log_level": "error",
  "message": "Database connection timeout",
  "exception": "TimeoutError",
  "stack_trace": "...",
  "response_time": 5020,
  "timestamp": 1695000000000
}
```

---

### 5. Financial Transactions

**Use Cases:** Fraud detection, compliance reporting, transaction analytics

**Variables:**
- `pipeline_name` (default: `financial-transactions`) - Pipeline identifier
- `fraud_threshold` (default: `0.02`) - Contamination rate for fraud detection (0.01-0.05)
- `aggregation_window` (default: `1h`) - Time window for transaction aggregation (15m, 1h, 6h)

**What it does:**
- Validates transaction_id, user_id, amount (0.01-1M range)
- Hashes account numbers and routing numbers
- Flags transactions >$10K for CTR compliance
- Detects fraudulent transactions using Isolation Forest
- Aggregates total volume, transaction count, avg/max size per user

**Sample event:**
```json
{
  "transaction_id": "txn_abc123",
  "user_id": "user_456",
  "account_number": "1234567890",
  "routing_number": "021000021",
  "amount": 250.00,
  "currency": "usd",
  "transaction_type": "payment",
  "merchant": "Amazon",
  "timestamp": 1695000000000
}
```

---

## Usage

### Python SDK

```python
from streamforge import StreamForge

sf = StreamForge('https://your-api-url.com')

# List all templates
templates = sf.list_templates()
print(f"Available templates: {templates['count']}")

# Get template details
template = sf.get_template('ecommerce')
print(f"Variables: {template['template']['variables']}")

# Create pipeline from template
pipeline = sf.create_from_template('ecommerce', {
    'pipeline_name': 'my-shop-events',
    'anomaly_threshold': '0.03',
    'aggregation_window': '15m'
})
print(f"Created pipeline: {pipeline['pipeline_id']}")

# Start sending events
sf.ingest('my-shop-events', [
    {
        'user_id': 'user_001',
        'email': 'buyer@example.com',
        'event_type': 'purchase',
        'amount': 149.99,
        'product_id': 'laptop_pro',
        'timestamp': int(time.time() * 1000)
    }
])
```

---

### Node.js SDK

```typescript
import { StreamForge } from 'streamforge';

const sf = new StreamForge({ apiUrl: 'https://your-api-url.com' });

// List templates
const templates = await sf.listTemplates();
console.log(`Available templates: ${templates.count}`);

// Create from template
const pipeline = await sf.createFromTemplate('iot-sensors', {
  pipeline_name: 'factory-floor-sensors',
  sensor_field: 'temperature',
  zscore_threshold: '3.0',
  aggregation_window: '5m'
});

// Ingest sensor data
await sf.ingest('factory-floor-sensors', [
  {
    device_id: 'temp_sensor_01',
    sensor_type: 'temperature',
    temperature: 185.3,
    location: 'assembly_line_1',
    timestamp: Date.now()
  }
]);
```

---

### CLI

```bash
# List all templates
streamforge templates list

# Output:
# Available templates:
# - ecommerce: E-Commerce Events (fraud detection, revenue tracking)
# - iot-sensors: IoT Sensor Data (predictive maintenance, quality control)
# - web-analytics: Web Analytics (conversion tracking, GDPR compliance)
# - application-logs: Application Logs (error tracking, performance monitoring)
# - financial-transactions: Financial Transactions (fraud detection, compliance)

# Get template details
streamforge templates get ecommerce

# Create pipeline from template
streamforge create from-template ecommerce \
  --name my-shop-events \
  --var anomaly_threshold=0.03 \
  --var aggregation_window=15m

# Ingest events
streamforge ingest my-shop-events events.json
```

---

### REST API

```bash
# List templates
curl https://your-api-url.com/v1/templates

# Get template details
curl https://your-api-url.com/v1/templates/ecommerce

# Create from template
curl -X POST https://your-api-url.com/v1/pipelines/from-template \
  -H "Content-Type: application/json" \
  -H "X-Org-Id: your-org" \
  -d '{
    "template_id": "ecommerce",
    "variables": {
      "pipeline_name": "my-shop-events",
      "anomaly_threshold": "0.03",
      "aggregation_window": "15m"
    }
  }'
```

---

## When to Use Templates vs Custom Pipelines

### Use Templates When:
- ✅ Getting started quickly
- ✅ Your use case matches a template (e-commerce, IoT, logs, etc.)
- ✅ You want production-ready anomaly detection and aggregations
- ✅ Standard transforms are sufficient (validation, hashing, casting)

### Build Custom Pipelines When:
- ✅ Complex multi-step transformations (regex, GeoIP, SQL-like joins)
- ✅ Custom validation rules beyond type checking
- ✅ Domain-specific aggregations (e.g., churn rate, NPS score)
- ✅ Integration with external systems (webhooks, ML models)

---

## Template Customization

### Override Steps After Creation

```python
# Create from template
pipeline = sf.create_from_template('ecommerce', {'pipeline_name': 'my-shop'})

# Get pipeline config
config = sf.get_pipeline('my-shop')

# Modify steps (add custom transform)
config['pipeline']['steps'].append({
    'type': 'transform',
    'operations': [
        {'op': 'extract', 'field': 'user_agent', 'pattern': '.*Chrome.*', 'to': 'is_chrome'}
    ]
})

# Update pipeline (requires PATCH endpoint, coming in Day 3)
```

---

## Best Practices

1. **Start with a template** - Even if you need customization, templates provide solid defaults
2. **Test with sample events** - Each template includes sample events - use them to verify output
3. **Monitor anomaly rates** - Check CloudWatch dashboard after first ingestion to tune thresholds
4. **Version your variables** - Store template variables in source control for reproducibility
5. **Use descriptive pipeline names** - `prod-checkout-fraud-detection` > `pipeline-123`

---

## Template Lifecycle

```
┌─────────────────┐
│  List Templates │  GET /v1/templates
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Get Template   │  GET /v1/templates/{id}
│  (with vars)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Instantiate    │  POST /v1/pipelines/from-template
│  with Variables │  {'template_id': 'ecommerce', 'variables': {...}}
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Pipeline Ready │  Start ingesting events
└─────────────────┘
```

---

## Coming Soon

- **Custom Templates** - Save your own pipelines as reusable templates
- **Template Marketplace** - Share templates with the community
- **Version Control** - Track template changes over time
- **A/B Testing** - Deploy two template variants and compare metrics

---

## Template Schema Reference

Each template JSON file contains:

```typescript
{
  id: string,              // Unique template identifier
  name: string,            // Human-readable name
  description: string,     // One-line description
  category: string,        // retail | industrial | marketing | observability | fintech
  variables: {             // Customizable parameters
    [key: string]: {
      description: string,
      default: string | number,
      required: boolean
    }
  },
  config: {                // Pipeline configuration (with {{variable}} placeholders)
    name: string,
    steps: Array<PipelineStep>,
    detect_anomalies: boolean,
    aggregate: boolean
  },
  sample_event: object     // Example event for testing
}
```

---

## Need Help?

- **Template not working?** Check sample events match your data structure
- **Anomalies not detected?** Tune `contamination` or `threshold` variables
- **Aggregations empty?** Verify time windows match your ingestion rate
- **Custom use case?** Open an issue or build a custom pipeline

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
