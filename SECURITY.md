# Security & Compliance

Enterprise-grade security controls and compliance automation for StreamForge.

---

## Overview

StreamForge implements defense-in-depth security with encryption, access controls, audit logging, and automated compliance checks for GDPR, HIPAA, and SOC2.

| Security Layer | Implementation | Compliance |
|----------------|----------------|------------|
| **Data at Rest** | KMS encryption (S3, DynamoDB) | HIPAA § 164.312(a)(2)(iv) |
| **Data in Transit** | TLS 1.2+, API Gateway HTTPS | HIPAA § 164.312(e)(2)(i) |
| **Field-Level Encryption** | PII fields encrypted with envelope encryption | GDPR Article 32 |
| **Access Controls** | IAM least-privilege policies, VPC endpoints | HIPAA § 164.312(a)(1) |
| **Audit Logging** | CloudWatch + CloudTrail integration | GDPR Article 30, HIPAA § 164.312(b) |
| **Network Isolation** | VPC with private subnets, security groups | SOC2 CC6.6 |

---

## Encryption

### Data at Rest (KMS)

All sensitive data encrypted using AWS KMS with customer-managed keys (CMKs).

**Python SDK:**
```python
from streamforge.security import KMSEncryption

kms = KMSEncryption('arn:aws:kms:us-east-1:123456789012:key/12345678-...')

# Encrypt sensitive data
ciphertext = kms.encrypt('sensitive-data')

# Decrypt
plaintext = kms.decrypt(ciphertext)
```

**Encrypted Resources:**
- S3 data lake (all zones: raw, clean, aggregated)
- DynamoDB tables (pipelines, runs, alerts)
- Kinesis stream encryption
- Lambda environment variables

**Key Rotation:** Automatic annual rotation enabled for all KMS keys.

---

### Field-Level Encryption (PII)

Automatic encryption for personally identifiable information (PII) fields.

**Supported PII Fields:**
- `email`, `phone`, `ssn`, `credit_card`
- `ip_address`, `address`, `name`, `date_of_birth`

**Python SDK:**
```python
from streamforge.security import FieldLevelEncryption

encryption = FieldLevelEncryption(kms_key_id='arn:aws:kms:...')

# Encrypt PII automatically
event = {
    'user_id': '12345',
    'email': 'user@example.com',
    'amount': 99.99
}

encrypted = encryption.encrypt_event(event)
# encrypted['email'] is now ciphertext
# encrypted['_pii_encrypted'] = True

# Decrypt when authorized
decrypted = encryption.decrypt_event(encrypted)
# decrypted['email'] = 'user@example.com'
```

**Custom PII Fields:**
```python
encrypted = encryption.encrypt_event(event, custom_pii_fields=['employee_id', 'salary'])
```

---

### Data in Transit

All network traffic encrypted with TLS 1.2+.

**API Gateway:** HTTPS-only endpoints with TLS 1.2 minimum  
**Lambda → Services:** AWS SDK uses HTTPS by default  
**VPC Endpoints:** Private connectivity to AWS services (no internet)

---

## Access Controls

### IAM Policies (Least Privilege)

StreamForge generates least-privilege IAM policies per pipeline.

**Example Policy:**
```python
from streamforge.security import generate_iam_policy

policy = generate_iam_policy(
    pipeline_id='ecommerce',
    resources=[
        'arn:aws:s3:::streamforge-lake/ecommerce/*',
        'arn:aws:dynamodb:us-east-1:123456789012:table/streamforge-pipelines',
        'arn:aws:kinesis:us-east-1:123456789012:stream/streamforge-events'
    ]
)
```

**Generated Policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "StreamForgeEcommerceAccess",
    "Effect": "Allow",
    "Action": [
      "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
      "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query",
      "kinesis:PutRecord", "kinesis:PutRecords",
      "kms:Decrypt", "kms:Encrypt"
    ],
    "Resource": [/* scoped to pipeline resources only */]
  }]
}
```

**Key Principles:**
- No wildcards (`*`) in resource ARNs
- Scoped to specific pipeline resources
- Read-only where possible
- No admin/root permissions

---

### VPC Isolation

Lambda functions run in VPC with private subnets (no public IP).

**CDK Configuration:**
```typescript
// infrastructure/lib/security-stack.ts
const vpc = new ec2.Vpc(this, 'StreamForgeVPC', {
  maxAzs: 2,
  natGateways: 1,
  subnetConfiguration: [{
    name: 'Private',
    subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
    cidrMask: 24
  }]
});

// VPC Endpoints (no internet egress)
vpc.addInterfaceEndpoint('DynamoDBEndpoint', {
  service: ec2.InterfaceVpcEndpointAwsService.DYNAMODB
});

vpc.addGatewayEndpoint('S3Endpoint', {
  service: ec2.GatewayVpcEndpointAwsService.S3
});

// Lambda in VPC
new lambda.Function(this, 'SecureFunction', {
  vpc: vpc,
  vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
  securityGroups: [securityGroup]
});
```

**Security Groups:** Egress-only rules, no inbound from internet.

---

## Audit Logging

All data access and administrative actions logged to CloudWatch + CloudTrail.

### CloudWatch Audit Logs

**Python SDK:**
```python
from streamforge.security import AuditLogger

audit = AuditLogger(log_group='/streamforge/audit')

# Log data access
audit.log_data_access(
    pipeline_id='ecommerce',
    user_id='user-123',
    query='SELECT * FROM events WHERE date=2026-09-28',
    row_count=1500
)

# Log PII access (GDPR/HIPAA requirement)
audit.log_pii_access(
    pipeline_id='ecommerce',
    user_id='user-123',
    pii_fields=['email', 'phone']
)

# Log administrative action
audit.log_event(
    action='pipeline.delete',
    resource='pipeline-456',
    user_id='admin-789',
    result='success',
    metadata={'reason': 'project sunset'}
)
```

**Audit Log Format:**
```json
{
  "timestamp": "2026-09-28T14:32:15Z",
  "action": "data.access",
  "resource": "pipeline-ecommerce",
  "user_id": "user-123",
  "result": "success",
  "metadata": {
    "query": "SELECT * FROM events WHERE date='2026-09-28'",
    "row_count": 1500
  }
}
```

**Retention:** 90 days (configurable), exported to S3 Glacier for long-term storage.

---

### CloudTrail Integration

AWS CloudTrail automatically logs all AWS API calls (S3, DynamoDB, Lambda, KMS).

**Logged Events:**
- S3 object access (GetObject, PutObject)
- DynamoDB table operations
- KMS encrypt/decrypt calls
- Lambda invocations
- IAM role assumptions

**CloudTrail Configuration:**
```typescript
new cloudtrail.Trail(this, 'StreamForgeTrail', {
  bucket: trailBucket,
  includeGlobalServiceEvents: true,
  isMultiRegionTrail: true,
  enableFileValidation: true  // Tamper detection
});
```

---

## Compliance Automation

Automated compliance checks for GDPR, HIPAA, and SOC2.

### GDPR Compliance

**Python SDK:**
```python
from streamforge.security import ComplianceChecker

compliance = ComplianceChecker()

pipeline_config = {
    'pii_encryption_enabled': True,
    'data_retention_days': 90,
    'audit_logging_enabled': True
}

report = compliance.check_gdpr_compliance(pipeline_config)

if not report['compliant']:
    for violation in report['violations']:
        print(f"❌ {violation['rule']}: {violation['violation']}")
```

**GDPR Requirements Checked:**
- **Article 32** (Security of processing) - PII encryption
- **Article 5(1)(e)** (Storage limitation) - Data retention policy
- **Article 30** (Records of processing) - Audit logging

**Sample Report:**
```json
{
  "compliant": false,
  "violations": [{
    "rule": "GDPR Article 32 - Security of processing",
    "violation": "PII encryption not enabled",
    "severity": "high"
  }],
  "checked_at": "2026-09-28T14:32:15Z"
}
```

---

### HIPAA Compliance

**Python SDK:**
```python
pipeline_config = {
    'encryption_at_rest': True,
    'encryption_in_transit': True,
    'access_controls_enabled': True,
    'audit_logging_enabled': True
}

report = compliance.check_hipaa_compliance(pipeline_config)
```

**HIPAA Security Rule Requirements:**
- **§ 164.312(a)(2)(iv)** - Encryption at rest (KMS)
- **§ 164.312(e)(2)(i)** - Encryption in transit (TLS 1.2+)
- **§ 164.312(a)(1)** - Access controls (IAM least-privilege)
- **§ 164.312(b)** - Audit controls (CloudWatch + CloudTrail)

---

## Best Practices

### 1. Enable Encryption by Default

```python
# BAD: No encryption
sf.create_pipeline({
    'name': 'ecommerce',
    'encryption_enabled': False  # ❌ Non-compliant
})

# GOOD: Encryption enabled
sf.create_pipeline({
    'name': 'ecommerce',
    'encryption_enabled': True,
    'kms_key_id': 'arn:aws:kms:...'
})
```

---

### 2. Use Field-Level Encryption for PII

```python
# Automatically encrypt PII fields
encryption = FieldLevelEncryption(kms_key_id='...')

events = [
    {'user_id': '123', 'email': 'user@example.com', 'amount': 99.99},
    {'user_id': '456', 'email': 'admin@example.com', 'amount': 149.99}
]

encrypted_events = [encryption.encrypt_event(e) for e in events]
```

---

### 3. Log All Data Access

```python
# Log every query for audit trail
audit = AuditLogger()

result = sf.query('SELECT * FROM events WHERE user_id=123')

audit.log_data_access(
    pipeline_id='ecommerce',
    user_id=current_user_id,
    query=query,
    row_count=len(result['rows'])
)
```

---

### 4. Run Compliance Checks in CI/CD

```bash
# .github/workflows/compliance.yml
- name: Check Compliance
  run: |
    python -c "
    from streamforge.security import ComplianceChecker
    compliance = ComplianceChecker()
    report = compliance.check_gdpr_compliance(config)
    assert report['compliant'], 'GDPR violations detected'
    "
```

---

### 5. Rotate KMS Keys Annually

KMS automatic key rotation enabled:
```typescript
const kmsKey = new kms.Key(this, 'StreamForgeKey', {
  enableKeyRotation: true  // Annual rotation
});
```

---

## Security Incident Response

### 1. Detect Unauthorized Access

CloudWatch Logs Insights query:
```sql
fields @timestamp, action, user_id, resource, result
| filter result = "failure" or result = "denied"
| sort @timestamp desc
```

---

### 2. Investigate Data Breach

```python
# Find all PII access in last 7 days
audit = AuditLogger()

# Query CloudWatch Logs
logs = boto3.client('logs')

response = logs.filter_log_events(
    logGroupName='/streamforge/audit',
    filterPattern='{ $.action = "pii.access" }',
    startTime=int((datetime.utcnow() - timedelta(days=7)).timestamp() * 1000)
)

for event in response['events']:
    data = json.loads(event['message'])
    print(f"PII accessed by {data['user_id']} on {data['timestamp']}")
```

---

### 3. Revoke Compromised Credentials

```bash
# Disable IAM user immediately
aws iam delete-access-key --user-name compromised-user --access-key-id AKIA...

# Rotate KMS keys
aws kms schedule-key-deletion --key-id <key-id> --pending-window-in-days 7
```

---

## Cost Analysis

| Security Feature | Monthly Cost (100K events/day) |
|------------------|--------------------------------|
| KMS encryption | $1/key + $0.03/10K requests = ~$10 |
| CloudWatch audit logs (10 GB) | $0.50/GB = $5 |
| CloudTrail | $2/100K events = $60 |
| VPC endpoints | $7.20/endpoint × 3 = $21.60 |
| NAT Gateway | $32.40/month + data transfer |
| **Total** | **~$130/month** |

**Cost Optimization:**
- Use S3 VPC endpoint (free) instead of NAT for S3 access
- Sample CloudTrail events (e.g., 10% for development pipelines)
- Compress audit logs before archiving to S3 Glacier

---

## Roadmap

- **Data masking** - Automatic PII redaction for analytics queries
- **Secrets management** - Integration with AWS Secrets Manager
- **SOC2 compliance** - Automated controls for CC6.x requirements
- **Anomaly detection** - ML-powered access pattern monitoring
- **RBAC** - Role-based access control with fine-grained permissions

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
