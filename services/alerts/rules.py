"""
Custom alert rules engine for StreamForge.

Operators define declarative rules over pipeline metrics — "fire a WARNING if
avg latency exceeds 5s", "fire CRITICAL if the anomaly rate is above 5% AND
throughput has collapsed below 10 events/sec". This module stores those rules,
evaluates them against a metrics snapshot, and returns the alerts that should
fire, honoring a per-rule cooldown so a sustained breach doesn't spam.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from enum import Enum
import boto3
from aws_lambda_powertools import Logger

logger = Logger()

dynamodb = boto3.resource('dynamodb')


class Operator(Enum):
    """Comparison operators for rule conditions."""
    GT = "gt"            # >
    GTE = "gte"          # >=
    LT = "lt"            # <
    LTE = "lte"          # <=
    EQ = "eq"            # ==
    NEQ = "neq"          # !=


class LogicalOp(Enum):
    """How multiple conditions in a rule combine."""
    AND = "and"
    OR = "or"


def _compare(value: float, operator: str, threshold: float) -> bool:
    """Evaluate `value <operator> threshold`."""
    ops = {
        Operator.GT.value: lambda a, b: a > b,
        Operator.GTE.value: lambda a, b: a >= b,
        Operator.LT.value: lambda a, b: a < b,
        Operator.LTE.value: lambda a, b: a <= b,
        Operator.EQ.value: lambda a, b: a == b,
        Operator.NEQ.value: lambda a, b: a != b,
    }
    fn = ops.get(operator)
    if fn is None:
        raise ValueError(f"Unknown operator: {operator}")
    return fn(value, threshold)


class AlertRulesEngine:
    """Stores and evaluates custom alert rules against metric snapshots."""

    def __init__(self):
        self.rules_table = dynamodb.Table('streamforge-alert-rules')
        self.state_table = dynamodb.Table('streamforge-alert-rule-state')

    def create_rule(
        self,
        pipeline_id: str,
        name: str,
        conditions: List[Dict[str, Any]],
        severity: str,
        logical_op: str = LogicalOp.AND.value,
        cooldown_minutes: int = 15,
        enabled: bool = True
    ) -> Dict[str, Any]:
        """
        Create or update an alert rule.

        Args:
            pipeline_id: Pipeline the rule applies to
            name: Human-readable rule name (unique per pipeline)
            conditions: List of {metric, operator, threshold} dicts
            severity: Severity to emit when the rule fires
            logical_op: 'and' / 'or' — how conditions combine
            cooldown_minutes: Minimum minutes between re-firing this rule
            enabled: Whether the rule is active

        Returns:
            The stored rule record
        """
        if not conditions:
            raise ValueError("A rule must have at least one condition")

        for cond in conditions:
            if not all(k in cond for k in ('metric', 'operator', 'threshold')):
                raise ValueError("Each condition needs 'metric', 'operator', and 'threshold'")
            # Validate operator up front so bad rules are rejected at creation
            Operator(cond['operator'])

        rule_id = f"{pipeline_id}:{name}"
        rule = {
            'rule_id': rule_id,
            'pipeline_id': pipeline_id,
            'name': name,
            'conditions': conditions,
            'severity': severity,
            'logical_op': logical_op,
            'cooldown_minutes': cooldown_minutes,
            'enabled': enabled,
            'created_at': datetime.utcnow().isoformat()
        }

        self.rules_table.put_item(Item=rule)
        return rule

    def list_rules(self, pipeline_id: str) -> List[Dict[str, Any]]:
        """List all rules for a pipeline."""
        response = self.rules_table.query(
            KeyConditionExpression='pipeline_id = :pid',
            ExpressionAttributeValues={':pid': pipeline_id}
        )
        return response.get('Items', [])

    def evaluate_rule(
        self,
        rule: Dict[str, Any],
        metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate a single rule against a metrics snapshot.

        Returns:
            Dict with 'triggered' (bool) and 'matched_conditions' (list of
            the conditions that evaluated true, for the alert message).
        """
        conditions = rule['conditions']
        logical_op = rule.get('logical_op', LogicalOp.AND.value)

        results = []
        matched = []

        for cond in conditions:
            metric = cond['metric']
            if metric not in metrics:
                # A missing metric can't satisfy a condition
                results.append(False)
                continue

            value = metrics[metric]
            try:
                passed = _compare(float(value), cond['operator'], float(cond['threshold']))
            except (ValueError, TypeError):
                passed = False

            results.append(passed)
            if passed:
                matched.append({
                    'metric': metric,
                    'operator': cond['operator'],
                    'threshold': cond['threshold'],
                    'actual': value
                })

        if logical_op == LogicalOp.OR.value:
            triggered = any(results)
        else:
            triggered = all(results) and len(results) > 0

        return {'triggered': triggered, 'matched_conditions': matched}

    def evaluate_all(
        self,
        pipeline_id: str,
        metrics: Dict[str, Any],
        now: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Evaluate every enabled rule for a pipeline against a metrics snapshot.

        Rules whose cooldown has not elapsed since they last fired are skipped,
        so a sustained breach produces one alert per cooldown window, not a flood.

        Returns:
            List of alert payloads for rules that fired this evaluation.
        """
        now = now or datetime.utcnow()
        rules = self.list_rules(pipeline_id)
        alerts = []

        for rule in rules:
            if not rule.get('enabled', True):
                continue

            result = self.evaluate_rule(rule, metrics)
            if not result['triggered']:
                continue

            if self._in_cooldown(rule, now):
                logger.info(f"Rule {rule['rule_id']} triggered but in cooldown; skipping")
                continue

            alert = self._build_alert(rule, result['matched_conditions'])
            alerts.append(alert)
            self._record_fire(rule['rule_id'], now)

        return alerts

    def _in_cooldown(self, rule: Dict[str, Any], now: datetime) -> bool:
        """Check whether a rule fired recently enough to still be cooling down."""
        response = self.state_table.get_item(Key={'rule_id': rule['rule_id']})
        state = response.get('Item')
        if not state or not state.get('last_fired_at'):
            return False

        cooldown = int(rule.get('cooldown_minutes', 15))
        last_fired = datetime.fromisoformat(state['last_fired_at'])
        return now < last_fired + timedelta(minutes=cooldown)

    def _record_fire(self, rule_id: str, now: datetime):
        """Persist the time a rule fired for cooldown tracking."""
        self.state_table.put_item(Item={
            'rule_id': rule_id,
            'last_fired_at': now.isoformat()
        })

    def _build_alert(
        self,
        rule: Dict[str, Any],
        matched_conditions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build the alert payload for a fired rule."""
        condition_text = ', '.join(
            f"{c['metric']} {c['operator']} {c['threshold']} (actual: {c['actual']})"
            for c in matched_conditions
        )

        return {
            'pipeline_id': rule['pipeline_id'],
            'alert_type': 'custom_rule',
            'severity': rule['severity'],
            'title': f"Alert rule triggered: {rule['name']}",
            'message': f"Rule '{rule['name']}' fired — {condition_text}",
            'metadata': {
                'rule_id': rule['rule_id'],
                'matched_conditions': matched_conditions
            }
        }

    def delete_rule(self, pipeline_id: str, name: str) -> Dict[str, Any]:
        """Delete a rule by name."""
        rule_id = f"{pipeline_id}:{name}"
        self.rules_table.delete_item(Key={'pipeline_id': pipeline_id, 'name': name})
        return {'rule_id': rule_id, 'status': 'deleted'}


# Lambda handler
def lambda_handler(event, context):
    """
    Lambda handler for alert rule evaluation and management.

    Triggered by:
    - Metric pipeline (POST evaluate with a metrics snapshot)
    - API (CRUD on rules)
    """
    engine = AlertRulesEngine()

    action = event.get('action')
    pipeline_id = event.get('pipeline_id')

    if not pipeline_id:
        return _response(400, {'error': 'pipeline_id is required'})

    try:
        if action == 'evaluate':
            metrics = event.get('metrics', {})
            alerts = engine.evaluate_all(pipeline_id, metrics)
            return _response(200, {'alerts': alerts, 'fired': len(alerts)})

        elif action == 'create':
            rule = engine.create_rule(
                pipeline_id=pipeline_id,
                name=event['name'],
                conditions=event['conditions'],
                severity=event.get('severity', 'warning'),
                logical_op=event.get('logical_op', 'and'),
                cooldown_minutes=int(event.get('cooldown_minutes', 15)),
                enabled=event.get('enabled', True)
            )
            return _response(201, rule)

        elif action == 'list':
            return _response(200, {'rules': engine.list_rules(pipeline_id)})

        elif action == 'delete':
            return _response(200, engine.delete_rule(pipeline_id, event['name']))

        else:
            return _response(400, {'error': f'Unknown action: {action}'})

    except (ValueError, KeyError) as e:
        return _response(400, {'error': str(e)})
    except Exception as e:
        logger.error(f"Alert rules error: {e}")
        return _response(500, {'error': str(e)})


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status_code,
        'body': json.dumps(body),
        'headers': {'Content-Type': 'application/json'}
    }
