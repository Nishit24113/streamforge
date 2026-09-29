# Cost Optimization

AWS cost tracking, anomaly detection, and actionable savings recommendations for StreamForge.

---

## Features

- **Real-Time Cost Tracking** - Monitor AWS spend by service and pipeline
- **Cost Anomaly Detection** - Automated alerts for unexpected cost spikes
- **Savings Recommendations** - AI-powered optimization suggestions
- **3-Month Forecast** - Predict future costs with AWS Cost Explorer
- **Per-Pipeline Costs** - Tag-based cost allocation for each pipeline

---

## Cost Dashboard

Access at: `https://dashboard.streamforge.com/cost`

**Includes:**
- Current month spend vs last 30 days
- Daily cost trend chart
- Cost breakdown by AWS service
- Anomaly alerts
- Optimization recommendations with potential savings
- 3-month cost forecast

---

## API

### Get Cost Report

```bash
curl https://api.streamforge.com/cost/report
```

**Response:**
```json
{
  "generated_at": "2026-09-29T10:00:00Z",
  "current_month": {
    "total": 142.50,
    "by_service": {
      "AWS Lambda": 32.40,
      "Amazon DynamoDB": 45.20,
      "Amazon S3": 25.10
    }
  },
  "recommendations": [{
    "service": "Lambda",
    "issue": "High Lambda cost: $32.40/month",
    "recommendation": "Use ARM64 (Graviton2) for 20% cost reduction",
    "potential_savings": 6.48,
    "priority": "high"
  }],
  "forecast": {
    "forecast": [
      {"month": "2026-10", "forecast": 150.00},
      {"month": "2026-11", "forecast": 155.00}
    ]
  }
}
```

---

### Get Optimization Recommendations

```bash
curl https://api.streamforge.com/cost/recommendations
```

---

### Get Pipeline Cost

```bash
curl https://api.streamforge.com/cost/pipeline/pipeline-123
```

**Response:**
```json
{
  "pipeline_id": "pipeline-123",
  "total_cost": 42.30,
  "by_service": {
    "AWS Lambda": 15.20,
    "Amazon Kinesis": 18.40,
    "Amazon S3": 8.70
  },
  "days": 30
}
```

---

## Optimization Recommendations

### 1. Lambda ARM64 (Graviton2)

**Savings:** 20% reduction in Lambda costs

```typescript
// CDK: Switch to ARM64
new lambda.Function(this, 'Function', {
  architecture: lambda.Architecture.ARM_64,  // Instead of X86_64
  runtime: lambda.Runtime.PYTHON_3_12
});
```

---

### 2. DynamoDB Auto-Scaling

**Savings:** 30% reduction in DynamoDB costs

```typescript
// CDK: Enable auto-scaling
const table = new dynamodb.Table(this, 'Table', {
  billingMode: dynamodb.BillingMode.PROVISIONED,
  readCapacity: 5,
  writeCapacity: 5
});

table.autoScaleReadCapacity({ minCapacity: 5, maxCapacity: 100 });
table.autoScaleWriteCapacity({ minCapacity: 5, maxCapacity: 100 });
```

---

### 3. S3 Intelligent-Tiering

**Savings:** 40% reduction in S3 storage costs

```typescript
// CDK: Enable Intelligent-Tiering
new s3.Bucket(this, 'DataLake', {
  lifecycleRules: [{
    transitions: [{
      storageClass: s3.StorageClass.INTELLIGENT_TIERING,
      transitionAfter: cdk.Duration.days(0)  // Immediate
    }]
  }]
});
```

---

### 4. CloudWatch Logs Retention

**Savings:** 67% reduction in CloudWatch Logs costs

```typescript
// CDK: Reduce retention from 90 to 30 days
new logs.LogGroup(this, 'Logs', {
  retention: logs.RetentionDays.ONE_MONTH  // Instead of THREE_MONTHS
});
```

---

### 5. Kinesis Provisioned Mode

**Savings:** 25% reduction if consistent throughput

```typescript
// Only if you have consistent throughput (not spiky)
new kinesis.Stream(this, 'Stream', {
  streamMode: kinesis.StreamMode.PROVISIONED,
  shardCount: 2  // Instead of on-demand
});
```

---

## Cost Anomaly Detection

Automated alerts when costs spike unexpectedly.

**Example Anomaly:**
```json
{
  "date": "2026-09-28",
  "service": "AWS Lambda",
  "expected_cost": 30.00,
  "actual_cost": 95.00,
  "impact": 65.00
}
```

**Slack Alert:**
```
⚠️ Cost Anomaly Detected
Service: AWS Lambda
Expected: $30.00
Actual: $95.00
Impact: +$65.00

Investigate: https://dashboard.streamforge.com/cost
```

---

## Per-Pipeline Cost Tracking

Track costs for individual pipelines using AWS Cost Allocation Tags.

### Enable Cost Allocation Tags

```bash
# Tag all resources with pipeline ID
aws resourcegroupstaggingapi tag-resources \
  --resource-arn-list arn:aws:lambda:us-east-1:123456789012:function:pipeline-123-* \
  --tags streamforge:pipeline=pipeline-123

# Activate cost allocation tag
aws ce update-cost-allocation-tags-status \
  --cost-allocation-tags-status TagKey=streamforge:pipeline,Status=Active
```

### CDK: Auto-Tag Resources

```typescript
// Automatically tag all resources in stack
Tags.of(stack).add('streamforge:pipeline', pipelineId);
```

---

## Cost Forecast

3-month cost prediction using AWS Cost Explorer ML models.

**Python SDK:**
```python
from streamforge import StreamForge

sf = StreamForge('https://api.streamforge.com')

forecast = sf.get_cost_forecast(months=3)

for month in forecast['forecast']:
    print(f"{month['month']}: ${month['forecast']} (±${month['upper_bound'] - month['lower_bound']})")
```

**Output:**
```
2026-10: $150.00 (±$30.00)
2026-11: $155.00 (±$31.00)
2026-12: $160.00 (±$32.00)
```

---

## Budget Alerts

Set monthly budget with SNS alerts.

```typescript
import * as budgets from 'aws-cdk-lib/aws-budgets';

new budgets.CfnBudget(this, 'MonthlyBudget', {
  budget: {
    budgetName: 'StreamForge-Monthly',
    budgetLimit: {
      amount: 200,
      unit: 'USD'
    },
    timeUnit: 'MONTHLY',
    budgetType: 'COST'
  },
  notificationsWithSubscribers: [{
    notification: {
      notificationType: 'ACTUAL',
      comparisonOperator: 'GREATER_THAN',
      threshold: 80  // Alert at 80% of budget
    },
    subscribers: [{
      subscriptionType: 'EMAIL',
      address: 'alerts@streamforge.com'
    }]
  }]
});
```

---

## Cost Benchmarks

Typical monthly costs for StreamForge by usage tier:

| Tier | Events/Day | Storage | Cost/Month |
|------|-----------|---------|------------|
| **Dev** | 10K | 1 GB | $15-20 |
| **Small** | 100K | 10 GB | $50-75 |
| **Medium** | 1M | 100 GB | $150-200 |
| **Large** | 10M | 1 TB | $500-750 |

**Cost Breakdown (Medium Tier):**
- Lambda: $30 (20%)
- DynamoDB: $45 (30%)
- S3: $25 (17%)
- Kinesis: $20 (13%)
- CloudWatch: $15 (10%)
- API Gateway: $10 (7%)
- Other: $5 (3%)

---

## Roadmap

- **Cost allocation reports** - Export per-pipeline costs to CSV
- **Savings Plans** - Automatically recommend Compute/EC2 Savings Plans
- **Reserved Capacity** - Identify opportunities for Reserved Capacity
- **Multi-account cost tracking** - Aggregate costs across AWS accounts

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
