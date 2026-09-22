"""End-to-end integration tests for the StreamForge processing pipeline.

Simulates the complete event lifecycle WITHOUT AWS by driving the actual
Python handler code through mock S3 and DynamoDB services.

Flow under test:
    validator -> transformer -> anomaly-detector -> aggregator
"""

import json
import math
import hashlib

import pytest

from tests.integration.conftest import (
    BUCKET,
    make_ecommerce_events,
    make_iot_events,
    make_web_analytics_events,
)


# ============================================================================
# Helpers
# ============================================================================


def _run_validator(handler, mock_s3, events, pipeline_config, pipeline_id="test", run_id="run-001"):
    """Seed events into mock S3 and invoke the validator handler."""
    key = f"raw/{pipeline_id}/{run_id}.json"
    mock_s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(events), ContentType="application/json")
    raw_location = f"s3://{BUCKET}/{key}"

    return handler.lambda_handler(
        {
            "pipeline_id": pipeline_id,
            "run_id": run_id,
            "raw_location": raw_location,
            "events_count": len(events),
            "pipeline_config": pipeline_config,
        },
        None,
    )


def _run_transformer(handler, mock_s3, events, pipeline_config, pipeline_id="test", run_id="run-001"):
    """Seed events into mock S3 and invoke the transformer handler."""
    key = f"raw/{pipeline_id}/{run_id}.json"
    mock_s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(events), ContentType="application/json")
    raw_location = f"s3://{BUCKET}/{key}"

    return handler.lambda_handler(
        {
            "pipeline_id": pipeline_id,
            "run_id": run_id,
            "raw_location": raw_location,
            "events_count": len(events),
            "pipeline_config": pipeline_config,
        },
        None,
    )


def _run_anomaly_detector(handler, mock_s3, events, pipeline_config, pipeline_id="test", run_id="run-001"):
    """Seed transformed events into mock S3 and invoke the anomaly-detector."""
    key = f"clean/{pipeline_id}/{run_id}.json"
    mock_s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(events), ContentType="application/json")
    clean_location = f"s3://{BUCKET}/{key}"

    return handler.lambda_handler(
        {
            "pipeline_id": pipeline_id,
            "run_id": run_id,
            "clean_location": clean_location,
            "events_count": len(events),
            "pipeline_config": pipeline_config,
        },
        None,
    )


def _run_aggregator(handler, mock_s3, events, pipeline_config, pipeline_id="test", run_id="run-001"):
    """Seed events into mock S3 and invoke the aggregator."""
    key = f"clean/{pipeline_id}/{run_id}.json"
    mock_s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(events), ContentType="application/json")
    clean_location = f"s3://{BUCKET}/{key}"

    return handler.lambda_handler(
        {
            "pipeline_id": pipeline_id,
            "run_id": run_id,
            "clean_location": clean_location,
            "events_count": len(events),
            "pipeline_config": pipeline_config,
        },
        None,
    )


# ============================================================================
# 1. Validation tests
# ============================================================================


class TestValidation:
    """Tests for the validator stage."""

    def test_valid_ecommerce_events_pass(self, validator_handler, mock_s3, ecommerce_config):
        """All well-formed e-commerce events should pass validation."""
        events = make_ecommerce_events(5)
        result = _run_validator(validator_handler, mock_s3, events, ecommerce_config, "ecommerce-events")

        assert result["valid_count"] == 5
        assert result["rejected_count"] == 0

    def test_invalid_events_rejected(self, validator_handler, mock_s3, ecommerce_config):
        """Events missing required fields or failing range checks are rejected."""
        events = make_ecommerce_events(5, include_invalid=True)
        result = _run_validator(validator_handler, mock_s3, events, ecommerce_config, "ecommerce-events")

        # 5 valid + 3 invalid (missing user_id, negative amount, null user_id)
        assert result["valid_count"] == 5
        assert result["rejected_count"] == 3

    def test_rejected_events_written_to_s3(self, validator_handler, mock_s3, ecommerce_config):
        """Rejected events should be persisted to S3 under the rejected/ prefix."""
        events = make_ecommerce_events(2, include_invalid=True)
        _run_validator(validator_handler, mock_s3, events, ecommerce_config, "ecommerce-events")

        rejected_keys = mock_s3.list_keys("test-bucket/rejected/")
        assert len(rejected_keys) > 0

    def test_iot_validation_range_checks(self, validator_handler, mock_s3, iot_config):
        """IoT events with sensor values outside -273.15..10000 are rejected."""
        events = make_iot_events(3)
        # Inject an event with value below absolute zero
        events.append({
            "event_id": "evt-iot-cold",
            "pipeline_id": "iot-sensors",
            "timestamp": 1000000,
            "source": "sensor",
            "event_type": "reading",
            "device_id": "device-0",
            "sensor_type": "temperature",
            "value": -300.0,
            "payload": json.dumps({
                "device_id": "device-0",
                "sensor_type": "temperature",
                "value": -300.0,
                "timestamp": 1000000,
            }),
        })

        result = _run_validator(validator_handler, mock_s3, events, iot_config, "iot-sensors")
        assert result["rejected_count"] == 1
        assert result["valid_count"] == 3

    def test_web_analytics_null_rejection(self, validator_handler, mock_s3, web_analytics_config):
        """Web analytics events with null page_url or session_id are rejected."""
        events = make_web_analytics_events(2)
        events.append({
            "event_id": "evt-web-null",
            "pipeline_id": "web-analytics",
            "timestamp": 1000000,
            "source": "tracker",
            "event_type": "pageview",
            "page_url": None,
            "session_id": "sess-1",
            "payload": json.dumps({
                "page_url": None,
                "session_id": "sess-1",
                "timestamp": 1000000,
            }),
        })

        result = _run_validator(validator_handler, mock_s3, events, web_analytics_config, "web-analytics")
        assert result["rejected_count"] == 1


# ============================================================================
# 2. Transformation tests
# ============================================================================


class TestTransformation:
    """Tests for the transformer stage."""

    def test_rename_operation(self, transformer_handler, mock_s3, ecommerce_config):
        """The rename op should move user_id -> customer_id in the payload."""
        events = make_ecommerce_events(1)
        result = _run_transformer(transformer_handler, mock_s3, events, ecommerce_config, "ecommerce-events")

        assert result["events_processed"] == 1

        # Retrieve the clean output from S3
        clean_keys = mock_s3.list_keys("test-bucket/clean/")
        assert len(clean_keys) > 0
        clean_events = json.loads(mock_s3.store[clean_keys[0]])

        payload = json.loads(clean_events[0]["payload"])
        assert "customer_id" in payload
        assert "user_id" not in payload

    def test_cast_operation(self, transformer_handler, mock_s3, ecommerce_config):
        """The cast op should convert amount to float (decimal)."""
        events = [{
            "event_id": "evt-cast",
            "pipeline_id": "ecommerce-events",
            "timestamp": 1000,
            "source": "api",
            "event_type": "purchase",
            "payload": json.dumps({
                "user_id": "u1",
                "action": "Purchase",
                "amount": "42",
                "timestamp": 1000,
            }),
        }]
        _run_transformer(transformer_handler, mock_s3, events, ecommerce_config, "ecommerce-events")

        clean_keys = mock_s3.list_keys("test-bucket/clean/")
        clean_events = json.loads(mock_s3.store[clean_keys[0]])
        payload = json.loads(clean_events[0]["payload"])
        assert isinstance(payload["amount"], float)
        assert payload["amount"] == 42.0

    def test_add_field_operations(self, transformer_handler, mock_s3, ecommerce_config):
        """$NOW and $UUID add_field operations produce values of the right types."""
        events = make_ecommerce_events(1)
        _run_transformer(transformer_handler, mock_s3, events, ecommerce_config, "ecommerce-events")

        clean_keys = mock_s3.list_keys("test-bucket/clean/")
        clean_events = json.loads(mock_s3.store[clean_keys[0]])
        payload = json.loads(clean_events[0]["payload"])

        assert "processed_at" in payload
        assert isinstance(payload["processed_at"], int)
        assert "event_id" in payload  # $UUID

    def test_hash_operation(self, transformer_handler, mock_s3, web_analytics_config):
        """The hash op should SHA-256 hash the ip_address field."""
        events = make_web_analytics_events(1)
        _run_transformer(transformer_handler, mock_s3, events, web_analytics_config, "web-analytics")

        clean_keys = mock_s3.list_keys("test-bucket/clean/")
        clean_events = json.loads(mock_s3.store[clean_keys[0]])
        payload = json.loads(clean_events[0]["payload"])

        # ip_address should now be a SHA-256 hex digest (64 chars)
        assert len(payload["ip_address"]) == 64
        # Verify it matches the expected hash
        expected = hashlib.sha256(b"192.168.1.0").hexdigest()
        assert payload["ip_address"] == expected

    def test_default_and_lowercase(self, transformer_handler, mock_s3, ecommerce_config):
        """default op fills missing currency; lowercase converts action."""
        events = [{
            "event_id": "evt-default",
            "pipeline_id": "ecommerce-events",
            "timestamp": 1000,
            "source": "api",
            "event_type": "purchase",
            "payload": json.dumps({
                "user_id": "u1",
                "action": "CHECKOUT",
                "amount": 10.0,
                "timestamp": 1000,
            }),
        }]
        _run_transformer(transformer_handler, mock_s3, events, ecommerce_config, "ecommerce-events")

        clean_keys = mock_s3.list_keys("test-bucket/clean/")
        clean_events = json.loads(mock_s3.store[clean_keys[0]])
        payload = json.loads(clean_events[0]["payload"])

        assert payload["currency"] == "USD"
        assert payload["action"] == "checkout"

    def test_transform_order_matters(self, transformer_handler, mock_s3, ecommerce_config):
        """Rename runs before add_field and cast; the final record reflects all ops in order."""
        events = make_ecommerce_events(1)
        _run_transformer(transformer_handler, mock_s3, events, ecommerce_config, "ecommerce-events")

        clean_keys = mock_s3.list_keys("test-bucket/clean/")
        clean_events = json.loads(mock_s3.store[clean_keys[0]])
        payload = json.loads(clean_events[0]["payload"])

        # After rename: customer_id exists, user_id gone
        assert "customer_id" in payload
        assert "user_id" not in payload
        # After cast: amount is float
        assert isinstance(payload["amount"], float)
        # After default: currency is set
        assert payload["currency"] == "USD"
        # After lowercase: action is lowered
        assert payload["action"] == payload["action"].lower()


# ============================================================================
# 3. Anomaly detection tests
# ============================================================================


class TestAnomalyDetection:
    """Tests for the anomaly-detector stage."""

    def test_zscore_detects_outlier(self, anomaly_handler, mock_s3, iot_config):
        """Z-score method flags extreme outliers in IoT readings."""
        # Create 20 normal events + 1 extreme outlier
        events = []
        for i in range(20):
            events.append({
                "event_id": f"evt-{i}",
                "pipeline_id": "iot-sensors",
                "timestamp": 1000 + i,
                "event_type": "reading",
                "payload": json.dumps({"value": 22.0 + (i % 3) * 0.5}),
                "is_anomaly": False,
                "anomaly_score": 0.0,
            })
        # Add outlier
        events.append({
            "event_id": "evt-outlier",
            "pipeline_id": "iot-sensors",
            "timestamp": 2000,
            "event_type": "reading",
            "payload": json.dumps({"value": 999.0}),
            "is_anomaly": False,
            "anomaly_score": 0.0,
        })

        result = _run_anomaly_detector(anomaly_handler, mock_s3, events, iot_config, "iot-sensors")
        assert result["anomalies_detected"] >= 1

    def test_normal_data_no_anomalies(self, anomaly_handler, mock_s3, iot_config):
        """Tightly clustered values should produce zero anomalies."""
        events = []
        for i in range(20):
            events.append({
                "event_id": f"evt-{i}",
                "pipeline_id": "iot-sensors",
                "timestamp": 1000 + i,
                "event_type": "reading",
                "payload": json.dumps({"value": 22.0}),
                "is_anomaly": False,
                "anomaly_score": 0.0,
            })

        result = _run_anomaly_detector(anomaly_handler, mock_s3, events, iot_config, "iot-sensors")
        assert result["anomalies_detected"] == 0

    def test_anomaly_flag_set_on_events(self, anomaly_handler, mock_s3, iot_config):
        """Detected anomalies should have is_anomaly=True and a positive anomaly_score."""
        events = []
        for i in range(20):
            events.append({
                "event_id": f"evt-{i}",
                "pipeline_id": "iot-sensors",
                "timestamp": 1000 + i,
                "event_type": "reading",
                "payload": json.dumps({"value": 22.0 + (i % 3) * 0.2}),
                "is_anomaly": False,
                "anomaly_score": 0.0,
            })
        events.append({
            "event_id": "evt-outlier",
            "pipeline_id": "iot-sensors",
            "timestamp": 2000,
            "event_type": "reading",
            "payload": json.dumps({"value": 500.0}),
            "is_anomaly": False,
            "anomaly_score": 0.0,
        })

        _run_anomaly_detector(anomaly_handler, mock_s3, events, iot_config, "iot-sensors")

        # Read back the written results from S3
        result_keys = [k for k in mock_s3.list_keys("test-bucket/clean/") if "anomaly" in k]
        assert len(result_keys) > 0
        result_events = json.loads(mock_s3.store[result_keys[0]])

        flagged = [e for e in result_events if e.get("is_anomaly")]
        assert len(flagged) >= 1
        for f in flagged:
            assert f["anomaly_score"] > 0


# ============================================================================
# 4. Aggregation tests
# ============================================================================


class TestAggregation:
    """Tests for the aggregator stage."""

    def test_sum_aggregation(self, aggregator_handler, mock_s3, ecommerce_config):
        """Sum metric correctly totals the amount field."""
        events = []
        amounts = [10.0, 20.0, 30.0, 40.0, 50.0]
        for i, amt in enumerate(amounts):
            events.append({
                "event_id": f"evt-{i}",
                "pipeline_id": "ecommerce-events",
                "timestamp": 1000,
                "event_type": "purchase",
                "action": "purchase",
                "payload": json.dumps({"amount": amt, "customer_id": f"c-{i}"}),
            })

        result = _run_aggregator(aggregator_handler, mock_s3, events, ecommerce_config, "ecommerce-events")
        assert result["aggregations_count"] >= 1

        # Read back aggregation output
        agg_keys = mock_s3.list_keys("test-bucket/agg/")
        assert len(agg_keys) > 0
        aggs = json.loads(mock_s3.store[agg_keys[0]])

        total_revenue = sum(a.get("total_revenue", 0) for a in aggs if a.get("total_revenue") is not None)
        assert total_revenue == pytest.approx(150.0)

    def test_avg_aggregation(self, aggregator_handler, mock_s3, ecommerce_config):
        """Avg metric computes the correct mean."""
        events = []
        amounts = [10.0, 20.0, 30.0]
        for i, amt in enumerate(amounts):
            events.append({
                "event_id": f"evt-{i}",
                "pipeline_id": "ecommerce-events",
                "timestamp": 1000,
                "event_type": "purchase",
                "action": "purchase",
                "payload": json.dumps({"amount": amt, "customer_id": f"c-{i}"}),
            })

        _run_aggregator(aggregator_handler, mock_s3, events, ecommerce_config, "ecommerce-events")

        agg_keys = mock_s3.list_keys("test-bucket/agg/")
        aggs = json.loads(mock_s3.store[agg_keys[0]])
        avg_values = [a["avg_order_value"] for a in aggs if "avg_order_value" in a]
        assert any(v == pytest.approx(20.0) for v in avg_values)

    def test_p95_aggregation(self, aggregator_handler, mock_s3, ecommerce_config):
        """P95 metric returns a value at or near the 95th percentile."""
        events = []
        for i in range(100):
            events.append({
                "event_id": f"evt-{i}",
                "pipeline_id": "ecommerce-events",
                "timestamp": 1000,
                "event_type": "purchase",
                "action": "purchase",
                "payload": json.dumps({"amount": float(i + 1), "customer_id": f"c-{i}"}),
            })

        _run_aggregator(aggregator_handler, mock_s3, events, ecommerce_config, "ecommerce-events")

        agg_keys = mock_s3.list_keys("test-bucket/agg/")
        aggs = json.loads(mock_s3.store[agg_keys[0]])
        p95_values = [a["p95_order_value"] for a in aggs if "p95_order_value" in a]
        # p95 of 1..100 should be around 95
        assert any(v >= 90 for v in p95_values)

    def test_group_by_produces_multiple_buckets(self, aggregator_handler, mock_s3, iot_config):
        """group_by [device_id, sensor_type] should produce separate aggregation buckets."""
        events = []
        for i in range(6):
            device = f"device-{i % 2}"
            events.append({
                "event_id": f"evt-{i}",
                "pipeline_id": "iot-sensors",
                "timestamp": 1000,
                "event_type": "reading",
                "device_id": device,
                "sensor_type": "temperature",
                "payload": json.dumps({
                    "device_id": device,
                    "sensor_type": "temperature",
                    "value": 22.0 + i,
                }),
            })

        result = _run_aggregator(aggregator_handler, mock_s3, events, iot_config, "iot-sensors")

        agg_keys = mock_s3.list_keys("test-bucket/agg/")
        aggs = json.loads(mock_s3.store[agg_keys[0]])
        groups = {a["group"] for a in aggs}
        # Should have at least 2 groups (device-0 and device-1)
        assert len(groups) >= 2


# ============================================================================
# 5. Pipeline config control-flow tests
# ============================================================================


class TestPipelineConfigFlow:
    """Tests that pipeline config flags control which stages run."""

    def test_pipeline_without_anomaly_step(self, anomaly_handler, mock_s3):
        """When no detect_anomalies steps are in config, default detection runs on numeric fields."""
        events = []
        for i in range(20):
            events.append({
                "event_id": f"evt-{i}",
                "pipeline_id": "no-anomaly",
                "timestamp": 1000 + i,
                "event_type": "generic",
                "payload": json.dumps({"value": 10.0}),
                "is_anomaly": False,
                "anomaly_score": 0.0,
            })

        config = {"steps": [], "detect_anomalies": False, "aggregate": False}
        result = _run_anomaly_detector(anomaly_handler, mock_s3, events, config, "no-anomaly")

        # With no detect_anomalies steps, falls back to auto-detect on numeric fields
        assert "anomalies_detected" in result

    def test_pipeline_without_aggregate_step(self, aggregator_handler, mock_s3):
        """When no aggregate steps exist, default aggregations are computed."""
        events = []
        for i in range(5):
            events.append({
                "event_id": f"evt-{i}",
                "pipeline_id": "no-agg",
                "timestamp": 1000 + i,
                "event_type": "generic",
                "payload": json.dumps({"metric": 10.0 + i}),
            })

        config = {"steps": [], "detect_anomalies": False, "aggregate": False}
        result = _run_aggregator(aggregator_handler, mock_s3, events, config, "no-agg")

        # Default aggregations should still be computed
        assert result["aggregations_count"] >= 1


# ============================================================================
# 6. Full pipeline end-to-end tests (all stages chained)
# ============================================================================


class TestFullPipeline:
    """End-to-end tests that chain all four stages together."""

    def test_ecommerce_full_pipeline(
        self, validator_handler, transformer_handler, anomaly_handler,
        aggregator_handler, mock_s3, ecommerce_config,
    ):
        """Complete e-commerce pipeline: validate -> transform -> detect -> aggregate."""
        events = make_ecommerce_events(10, include_invalid=True)
        pid = "ecommerce-events"
        rid = "run-e2e-ecom"

        # Stage 1: Validate
        val_result = _run_validator(validator_handler, mock_s3, events, ecommerce_config, pid, rid)
        assert val_result["valid_count"] == 10
        assert val_result["rejected_count"] == 3

        # Stage 2: Transform (use valid events -- re-seed only the valid ones)
        valid_events = [e for e in events if "user_id" in e and e.get("user_id") is not None
                        and e.get("amount", 0) >= 0]
        tx_result = _run_transformer(transformer_handler, mock_s3, valid_events, ecommerce_config, pid, rid)
        assert tx_result["events_processed"] == 10

        # Stage 3: Anomaly detection (read transformer output from S3)
        clean_keys = [k for k in mock_s3.list_keys(f"test-bucket/clean/{pid}") if "anomaly" not in k]
        assert len(clean_keys) > 0
        clean_events = json.loads(mock_s3.store[clean_keys[0]])

        ad_result = _run_anomaly_detector(anomaly_handler, mock_s3, clean_events, ecommerce_config, pid, rid)
        assert "anomalies_detected" in ad_result

        # Stage 4: Aggregate
        agg_result = _run_aggregator(aggregator_handler, mock_s3, clean_events, ecommerce_config, pid, rid)
        assert agg_result["aggregations_count"] >= 1

    def test_iot_full_pipeline(
        self, validator_handler, transformer_handler, anomaly_handler,
        aggregator_handler, mock_s3, iot_config,
    ):
        """Complete IoT pipeline: validate -> transform -> detect -> aggregate."""
        events = make_iot_events(20, include_outlier=True)
        pid = "iot-sensors"
        rid = "run-e2e-iot"

        # Stage 1: Validate
        val_result = _run_validator(validator_handler, mock_s3, events, iot_config, pid, rid)
        assert val_result["valid_count"] == 21  # 20 normal + 1 outlier (valid but extreme)
        assert val_result["rejected_count"] == 0

        # Stage 2: Transform
        tx_result = _run_transformer(transformer_handler, mock_s3, events, iot_config, pid, rid)
        assert tx_result["events_processed"] == 21

        # Stage 3: Anomaly detection
        clean_keys = [k for k in mock_s3.list_keys(f"test-bucket/clean/{pid}") if "anomaly" not in k]
        clean_events = json.loads(mock_s3.store[clean_keys[0]])

        ad_result = _run_anomaly_detector(anomaly_handler, mock_s3, clean_events, iot_config, pid, rid)
        # The extreme outlier (999.0) should be flagged
        assert ad_result["anomalies_detected"] >= 1

        # Stage 4: Aggregate
        agg_result = _run_aggregator(aggregator_handler, mock_s3, clean_events, iot_config, pid, rid)
        assert agg_result["aggregations_count"] >= 1

    def test_web_analytics_full_pipeline(
        self, validator_handler, transformer_handler, anomaly_handler,
        aggregator_handler, mock_s3, web_analytics_config,
    ):
        """Complete web analytics pipeline: validate -> transform -> detect -> aggregate."""
        events = make_web_analytics_events(10)
        pid = "web-analytics"
        rid = "run-e2e-web"

        # Stage 1: Validate
        val_result = _run_validator(validator_handler, mock_s3, events, web_analytics_config, pid, rid)
        assert val_result["valid_count"] == 10

        # Stage 2: Transform (hash ip, lowercase URL, add defaults)
        tx_result = _run_transformer(transformer_handler, mock_s3, events, web_analytics_config, pid, rid)
        assert tx_result["events_processed"] == 10

        # Verify hash was applied to ip_address
        clean_keys = [k for k in mock_s3.list_keys(f"test-bucket/clean/{pid}") if "anomaly" not in k]
        clean_events = json.loads(mock_s3.store[clean_keys[0]])
        first_payload = json.loads(clean_events[0]["payload"])
        assert len(first_payload.get("ip_address", "")) == 64  # SHA-256 hex length

        # Stage 3: Anomaly detection
        ad_result = _run_anomaly_detector(anomaly_handler, mock_s3, clean_events, web_analytics_config, pid, rid)
        assert "anomalies_detected" in ad_result

        # Stage 4: Aggregate
        agg_result = _run_aggregator(aggregator_handler, mock_s3, clean_events, web_analytics_config, pid, rid)
        assert agg_result["aggregations_count"] >= 1
