# Pipeline Health Scoring

One number per pipeline. Each pipeline emits many signals — error rate,
latency, anomaly rate, dead-letter-queue depth, replay recovery rate — and on
their own they tell fragmented stories. The health scorer folds them into a
single **0-100 score** and a **status tier**, so an operator can scan a fleet
and know exactly where to look.

---

## Status Tiers

| Score | Status | Meaning |
|-------|--------|---------|
| 90-100 | `healthy` | Operating normally |
| 70-89 | `degraded` | Some signals slipping; worth watching |
| 40-69 | `unhealthy` | Multiple signals bad; needs attention |
| 0-39 | `critical` | Severe; likely paging-worthy |

---

## Signals & Weights

Each signal contributes a weighted sub-score (0 = unhealthy, 1 = healthy).
Weights sum to 1.0; `error_rate` carries the most weight because it most
directly reflects data loss.

| Signal | Weight | Good → Bad |
|--------|--------|------------|
| `error_rate` | 0.30 | 0% → 10% |
| `latency` (ms) | 0.20 | 200ms → 5000ms |
| `anomaly_rate` | 0.20 | 1% → 15% |
| `dlq_depth` | 0.15 | 0 → 1000 msgs |
| `recovery_rate` | 0.15 | 100% → 0% (inverted) |

A signal at or better than its "good" bound scores 1.0; at or worse than "bad"
scores 0.0; in between it scales linearly.

---

## Usage

```python
from streamforge.health import HealthScorer

scorer = HealthScorer()

result = scorer.score({
    'error_rate': 0.02,
    'latency': 1200,
    'anomaly_rate': 0.03,
    'dlq_depth': 50,
    'recovery_rate': 0.95
})
# {
#   'score': 88.7,
#   'status': 'degraded',
#   'worst_signal': 'latency',
#   'breakdown': {'error_rate': {'value': 0.02, 'sub_score': 0.8, 'weight': 0.30}, ...}
# }
```

### Partial snapshots

Missing signals are excluded and the remaining weights are **renormalized**, so
a partial snapshot still yields a meaningful score:

```python
scorer.score({'latency': 200})     # -> score 100.0 (only signal, and it's perfect)
scorer.score({'error_rate': 0.05}) # -> score 50.0 (midpoint)
```

Non-numeric or `None` values are ignored rather than crashing evaluation.

---

## Fleet View

Score many pipelines at once; results come back **worst-first** so the most
troubled pipelines surface at the top. Unscoreable pipelines (no metrics) sort
last.

```python
ranked = scorer.score_many({
    'orders':   {'error_rate': 0.10, 'latency': 5000},
    'clicks':   {'error_rate': 0.00, 'latency': 200},
    'payments': {'error_rate': 0.05, 'latency': 1200},
})
# [orders (critical), payments (degraded), clicks (healthy)]
```

---

## Integration

The scorer consumes the same signals other services already produce:

- `error_rate`, `latency`, `anomaly_rate` — from the [real-time metrics](REALTIME.md)
- `dlq_depth` — from the [DLQ](DLQ.md) queue depth
- `recovery_rate` — from [DLQ metrics](DLQ.md#metrics-dashboard)

Scores pair naturally with [custom alert rules](ALERTS.md#custom-alert-rules) —
e.g. fire a CRITICAL alert when a pipeline's health score drops below 40.

```python
from streamforge.alerts import AlertRulesEngine

engine = AlertRulesEngine()
engine.create_rule(
    pipeline_id='orders',
    name='health-critical',
    conditions=[{'metric': 'health_score', 'operator': 'lt', 'threshold': 40}],
    severity='critical'
)
```

---

## Lambda API

```json
// action=score
{"action": "score", "pipeline_id": "orders", "metrics": {"error_rate": 0.02, "latency": 1200}}

// action=score_many
{"action": "score_many", "pipelines": {"orders": {...}, "clicks": {...}}}
```

---

## Score History & Trend Detection

A point-in-time score tells you where a pipeline *is*; the history tells you
where it's *heading*. Scores are persisted over time, and the series is analyzed
to classify a trend and — critically — to catch **gradual degradation**: a slow
decline that never trips a point-in-time threshold but quietly erodes a pipeline
over hours.

```python
from streamforge.health import HealthHistory

history = HealthHistory()

# Persist each score as it's computed
history.record_score('orders', score=85.0, status='degraded')

# Analyze the recent window for a slow decline
result = history.detect_gradual_degradation('orders', hours=6)
# {
#   'degrading': True,
#   'trend': 'degrading',
#   'current_score': 76,
#   'peak_score': 92,
#   'drop_from_peak': 16.0,
#   'slope': -4.0,       # ~4 points lost per sample
#   'change': -16.0,
#   'samples': 5
# }
```

### How the trend is classified

A least-squares **slope** is fit over the recent score series:

| Slope (points/sample) | Trend |
|-----------------------|-------|
| `<= -1.0` | `degrading` |
| `>= +1.0` | `improving` |
| in between | `stable` |
| fewer than 3 samples | `unknown` |

Missing (`None`) scores are filtered before analysis. This pairs with
[custom alert rules](ALERTS.md#custom-alert-rules): alert on `degrading` trends
*before* the absolute score reaches `critical`.

---

## Roadmap

- **Configurable weights** - Per-pipeline weight overrides
- **SLO budgets** - Translate scores into error-budget burn

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
