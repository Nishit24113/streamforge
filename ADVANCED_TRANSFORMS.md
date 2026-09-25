# Advanced Transforms

Powerful data transformation operations for complex ETL pipelines.

---

## Overview

StreamForge now supports advanced transforms beyond basic operations:

- **Regex Operations** - Extract, validate, and replace with patterns
- **URL Parsing** - Extract domains, query params, and URL components
- **GeoIP Lookup** - Convert IP addresses to geographic locations
- **User Agent Parsing** - Detect browser, OS, device type from UA strings

---

## Regex Operations

### Extract with Pattern

Extract substrings matching regex patterns.

**Configuration:**
```json
{
  "op": "regex_extract",
  "field": "email",
  "pattern": "@(.+)$",
  "group": 1,
  "target": "email_domain"
}
```

**Input:**
```json
{"email": "user@gmail.com"}
```

**Output:**
```json
{"email": "user@gmail.com", "email_domain": "gmail.com"}
```

**Common Use Cases:**
- Extract email domains: `@(.+)$`
- Extract phone area codes: `\((\d{3})\)`
- Extract hashtags from text: `#(\w+)`
- Parse log timestamps: `(\d{4}-\d{2}-\d{2})`

---

### Validate with Pattern

Validate fields against regex patterns.

**Configuration:**
```json
{
  "op": "regex_validate",
  "field": "email",
  "pattern": "^[\\w\\.-]+@[\\w\\.-]+\\.\\w+$"
}
```

**Input:**
```json
{"email": "invalid-email"}
```

**Output:**
```json
{"email": "invalid-email", "email_valid": false}
```

**Common Patterns:**
- Email: `^[\w\.-]+@[\w\.-]+\.\w+$`
- Phone (US): `^\+?1?\d{10}$`
- Credit card: `^\d{4}-?\d{4}-?\d{4}-?\d{4}$`
- ZIP code: `^\d{5}(-\d{4})?$`
- UUID: `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`

---

### Replace with Pattern

Replace substrings matching patterns.

**Configuration:**
```json
{
  "op": "regex_replace",
  "field": "ssn",
  "pattern": "\\d{3}-\\d{2}-\\d{4}",
  "replacement": "XXX-XX-XXXX"
}
```

**Input:**
```json
{"ssn": "123-45-6789"}
```

**Output:**
```json
{"ssn": "XXX-XX-XXXX"}
```

**Common Use Cases:**
- Redact SSNs: `\d{3}-\d{2}-\d{4}` → `XXX-XX-XXXX`
- Strip HTML tags: `<[^>]+>` → ``
- Remove extra whitespace: `\s+` → ` `
- Mask credit cards: `\d{4}` → `****` (keep last 4)

---

## URL Parsing

### Parse Full URL

Extract all URL components.

**Configuration:**
```json
{
  "op": "parse_url",
  "field": "page_url"
}
```

**Input:**
```json
{"page_url": "https://shop.example.com/products?id=123&sort=price"}
```

**Output:**
```json
{
  "page_url": "https://shop.example.com/products?id=123&sort=price",
  "url_scheme": "https",
  "url_domain": "shop.example.com",
  "url_path": "/products",
  "url_query": {"id": ["123"], "sort": ["price"]}
}
```

**Use Cases:**
- Track referrer domains
- Extract UTM campaign parameters
- Analyze traffic by subdomain
- Filter by URL path patterns

---

### Extract Domain

Extract root domain from URLs.

**Configuration:**
```json
{
  "op": "extract_domain",
  "field": "referrer",
  "include_subdomain": false
}
```

**Input:**
```json
{"referrer": "https://blog.company.com/post"}
```

**Output:**
```json
{"referrer": "https://blog.company.com/post", "domain": "company.com"}
```

**Examples:**
| URL | include_subdomain=false | include_subdomain=true |
|-----|-------------------------|------------------------|
| https://shop.example.com | example.com | shop.example.com |
| http://blog.company.co.uk | company.co.uk | blog.company.co.uk |
| https://www.site.org/page | site.org | www.site.org |

---

## GeoIP Lookup

Convert IP addresses to geographic locations.

**Configuration:**
```json
{
  "op": "geoip_lookup",
  "field": "ip_address"
}
```

**Input:**
```json
{"ip_address": "8.8.8.8"}
```

**Output:**
```json
{
  "ip_address": "8.8.8.8",
  "geo_country": "US",
  "geo_city": "Mountain View",
  "geo_region": "California"
}
```

**Use Cases:**
- Country-based analytics and segmentation
- Fraud detection (IP location vs billing address)
- Content localization recommendations
- Regional compliance (GDPR, data residency)

**Note:** Current implementation is simplified. For production, integrate:
- **MaxMind GeoIP2** - Most accurate, requires license
- **IP-API** - Free tier available (45 req/min)
- **ipstack** - Paid API with high accuracy

---

## User Agent Parsing

Parse browser, OS, and device type from user agent strings.

**Configuration:**
```json
{
  "op": "parse_user_agent",
  "field": "user_agent"
}
```

**Input:**
```json
{
  "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1"
}
```

**Output:**
```json
{
  "user_agent": "Mozilla/5.0...",
  "browser": "Safari",
  "os": "iOS",
  "device_type": "mobile",
  "is_mobile": true,
  "is_bot": false
}
```

**Detected Values:**

**Browsers:** Chrome, Firefox, Safari, Edge, Unknown  
**Operating Systems:** Windows, macOS, iOS, Android, Linux, Unknown  
**Device Types:** desktop, mobile, tablet

**Use Cases:**
- Mobile vs desktop traffic analysis
- Browser-specific feature targeting
- Bot/crawler filtering
- Cross-platform performance testing

---

## Pipeline Examples

### E-Commerce with Advanced Transforms

```json
{
  "name": "ecommerce-advanced",
  "steps": [
    {
      "type": "transform",
      "operations": [
        {
          "op": "regex_validate",
          "field": "email",
          "pattern": "^[\\w\\.-]+@[\\w\\.-]+\\.\\w+$"
        },
        {
          "op": "regex_extract",
          "field": "email",
          "pattern": "@(.+)$",
          "group": 1,
          "target": "email_domain"
        },
        {
          "op": "geoip_lookup",
          "field": "ip_address"
        },
        {
          "op": "parse_url",
          "field": "referrer"
        }
      ]
    }
  ]
}
```

**Scenario:** Validate customer emails, extract domain for analytics, determine country for shipping, track referral sources.

---

### Web Analytics with Device Detection

```json
{
  "name": "web-analytics-devices",
  "steps": [
    {
      "type": "transform",
      "operations": [
        {
          "op": "parse_user_agent",
          "field": "user_agent"
        },
        {
          "op": "parse_url",
          "field": "page_url"
        },
        {
          "op": "extract_domain",
          "field": "referrer",
          "include_subdomain": false
        }
      ]
    },
    {
      "type": "aggregate",
      "window": "1h",
      "group_by": ["device_type", "browser"],
      "metrics": [
        {"field": "user_id", "agg": "count_distinct", "alias": "unique_visitors"},
        {"field": "page_url", "agg": "count", "alias": "page_views"}
      ]
    }
  ]
}
```

**Scenario:** Track page views by device type and browser, aggregate hourly stats.

---

### Security Monitoring with IP Validation

```json
{
  "name": "security-logs",
  "steps": [
    {
      "type": "transform",
      "operations": [
        {
          "op": "geoip_lookup",
          "field": "ip_address"
        },
        {
          "op": "regex_validate",
          "field": "ip_address",
          "pattern": "^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$"
        },
        {
          "op": "parse_user_agent",
          "field": "user_agent"
        }
      ]
    },
    {
      "type": "detect_anomalies",
      "field": "failed_login_count",
      "method": "zscore",
      "threshold": 3.0
    }
  ]
}
```

**Scenario:** Track failed login attempts, detect suspicious IPs from unexpected countries, flag bot activity.

---

### Content Moderation with Regex Masking

```json
{
  "name": "user-content-moderation",
  "steps": [
    {
      "type": "transform",
      "operations": [
        {
          "op": "regex_replace",
          "field": "content",
          "pattern": "\\b\\d{3}-\\d{2}-\\d{4}\\b",
          "replacement": "[SSN REDACTED]"
        },
        {
          "op": "regex_replace",
          "field": "content",
          "pattern": "\\b\\d{16}\\b",
          "replacement": "[CARD REDACTED]"
        },
        {
          "op": "regex_extract",
          "field": "content",
          "pattern": "#(\\w+)",
          "target": "hashtags"
        }
      ]
    }
  ]
}
```

**Scenario:** Auto-redact PII from user-generated content, extract hashtags for trending analysis.

---

## Performance Considerations

### Regex Performance

**Fast patterns:** Simple character classes, anchors (`^`, `$`)  
**Slow patterns:** Backtracking (`.*`), nested quantifiers, lookahead/lookbehind

**Optimize:**
```javascript
// SLOW: .*@gmail\.com$
// FAST: [^@]+@gmail\.com$

// SLOW: (\w+\s+)+
// FAST: \w+(?:\s+\w+)*
```

---

### GeoIP Lookup

**Production recommendations:**
- Cache IP → Location mappings (Redis/DynamoDB)
- Batch lookups (send 100 IPs per request)
- Use edge locations (CloudFront + Lambda@Edge)

**Cost:**
- MaxMind GeoLite2: Free, 99.8% country accuracy
- MaxMind GeoIP2: $100/mo, 99.99% city accuracy
- IP-API: Free 45 req/min, $13/mo unlimited

---

### User Agent Parsing

**Production library:** `user-agents` (Python) or `ua-parser-js` (Node.js)

**Caching strategy:**
```python
# Cache parsed results (UA strings repeat frequently)
from functools import lru_cache

@lru_cache(maxsize=1000)
def parse_ua(ua_string):
    return user_agents.parse(ua_string)
```

---

## Testing Advanced Transforms

### Test Regex Extract

```bash
# Create test event
echo '[{"email": "user@gmail.com"}]' > test_event.json

# Create pipeline with regex extract
streamforge create test-regex --config '{
  "steps": [{
    "type": "transform",
    "operations": [{
      "op": "regex_extract",
      "field": "email",
      "pattern": "@(.+)$",
      "group": 1,
      "target": "domain"
    }]
  }]
}'

# Ingest and verify
streamforge ingest test-regex test_event.json

# Query results
streamforge query "SELECT payload FROM clean WHERE pipeline_id='test-regex'"
# Expected: {"email": "user@gmail.com", "domain": "gmail.com"}
```

---

### Test GeoIP Lookup

```python
from streamforge import StreamForge

sf = StreamForge('https://your-api-url.com')

# Create pipeline
sf.create_pipeline({
    'pipeline_id': 'test-geoip',
    'steps': [{
        'type': 'transform',
        'operations': [{
            'op': 'geoip_lookup',
            'field': 'ip_address'
        }]
    }]
})

# Test with sample IPs
sf.ingest('test-geoip', [
    {'ip_address': '8.8.8.8'},       # Google DNS (US)
    {'ip_address': '1.1.1.1'},       # Cloudflare (AU)
    {'ip_address': '192.168.1.1'},   # Private IP
])

# Check results
results = sf.query("SELECT * FROM clean WHERE pipeline_id='test-geoip'")
print(results['rows'])
```

---

## Limitations & Roadmap

### Current Limitations

- **GeoIP:** Simplified implementation (production needs MaxMind)
- **User Agent:** Basic parsing (missing versions, device models)
- **No SQL JOIN:** Single-pipeline transforms only
- **Regex:** No named capture groups yet

### Coming Soon

- **SQL JOIN support** - Combine events from multiple pipelines
- **Advanced GeoIP** - MaxMind GeoIP2 integration with city/ISP data
- **Machine Learning transforms** - Sentiment analysis, entity extraction
- **Custom Python UDFs** - Upload your own transform functions

---

## Best Practices

1. **Test patterns first** - Use regex101.com before deploying
2. **Cache expensive lookups** - GeoIP, user agent parsing
3. **Validate before transform** - Check field exists and is correct type
4. **Handle nulls gracefully** - Advanced ops return null for missing/invalid data
5. **Monitor transform performance** - CloudWatch dashboard shows Lambda duration

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
