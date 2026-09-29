"""
Cost Optimization Analyzer for StreamForge.

Tracks AWS spend across all services, identifies cost anomalies,
and provides actionable optimization recommendations.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
import boto3

# AWS clients
ce = boto3.client('ce')  # Cost Explorer
cloudwatch = boto3.client('cloudwatch')
dynamodb = boto3.resource('dynamodb')


class CostAnalyzer:
    """Analyzes AWS costs and provides optimization recommendations."""

    def __init__(self):
        self.cost_table = dynamodb.Table('streamforge-costs')

    def get_monthly_cost(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Get total cost for date range.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Cost breakdown by service
        """
        response = ce.get_cost_and_usage(
            TimePeriod={'Start': start_date, 'End': end_date},
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
        )

        costs_by_service = {}
        total_cost = 0

        for result in response['ResultsByTime']:
            for group in result['Groups']:
                service = group['Keys'][0]
                cost = float(group['Metrics']['UnblendedCost']['Amount'])

                if service not in costs_by_service:
                    costs_by_service[service] = 0

                costs_by_service[service] += cost
                total_cost += cost

        return {
            'total': round(total_cost, 2),
            'by_service': costs_by_service,
            'start_date': start_date,
            'end_date': end_date
        }

    def get_cost_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get daily cost trend for last N days.

        Args:
            days: Number of days to analyze

        Returns:
            List of daily cost records
        """
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days)

        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.isoformat(),
                'End': end_date.isoformat()
            },
            Granularity='DAILY',
            Metrics=['UnblendedCost']
        )

        trend = []
        for result in response['ResultsByTime']:
            trend.append({
                'date': result['TimePeriod']['Start'],
                'cost': round(float(result['Total']['UnblendedCost']['Amount']), 2)
            })

        return trend

    def detect_cost_anomalies(self) -> List[Dict[str, Any]]:
        """
        Detect unusual cost spikes using Cost Explorer anomaly detection.

        Returns:
            List of detected anomalies
        """
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=30)

        # Use Cost Explorer anomaly detection
        response = ce.get_anomalies(
            DateInterval={
                'StartDate': start_date.isoformat(),
                'EndDate': end_date.isoformat()
            },
            MaxResults=10
        )

        anomalies = []
        for anomaly in response.get('Anomalies', []):
            anomalies.append({
                'date': anomaly['AnomalyStartDate'],
                'service': anomaly.get('RootCauses', [{}])[0].get('Service', 'Unknown'),
                'impact': round(float(anomaly['Impact']['TotalImpact']), 2),
                'expected_cost': round(float(anomaly['Impact']['MaxImpact']), 2),
                'actual_cost': round(float(anomaly['Impact']['TotalImpact']) + float(anomaly['Impact']['MaxImpact']), 2)
            })

        return anomalies

    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """
        Generate cost optimization recommendations.

        Returns:
            List of actionable recommendations
        """
        recommendations = []

        # Get cost breakdown
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=30)
        cost_data = self.get_monthly_cost(start_date.isoformat(), end_date.isoformat())

        # Lambda optimization
        lambda_cost = cost_data['by_service'].get('AWS Lambda', 0)
        if lambda_cost > 50:
            recommendations.append({
                'service': 'Lambda',
                'issue': f'High Lambda cost: ${lambda_cost:.2f}/month',
                'recommendation': 'Use ARM64 (Graviton2) for 20% cost reduction',
                'potential_savings': round(lambda_cost * 0.2, 2),
                'priority': 'high'
            })

        # DynamoDB optimization
        dynamodb_cost = cost_data['by_service'].get('Amazon DynamoDB', 0)
        if dynamodb_cost > 100:
            recommendations.append({
                'service': 'DynamoDB',
                'issue': f'High DynamoDB cost: ${dynamodb_cost:.2f}/month',
                'recommendation': 'Switch from on-demand to provisioned capacity with auto-scaling',
                'potential_savings': round(dynamodb_cost * 0.3, 2),
                'priority': 'high'
            })

        # S3 optimization
        s3_cost = cost_data['by_service'].get('Amazon Simple Storage Service', 0)
        if s3_cost > 50:
            recommendations.append({
                'service': 'S3',
                'issue': f'High S3 storage cost: ${s3_cost:.2f}/month',
                'recommendation': 'Enable S3 Intelligent-Tiering for automatic cost optimization',
                'potential_savings': round(s3_cost * 0.4, 2),
                'priority': 'medium'
            })

        # Kinesis optimization
        kinesis_cost = cost_data['by_service'].get('Amazon Kinesis', 0)
        if kinesis_cost > 30:
            recommendations.append({
                'service': 'Kinesis',
                'issue': f'High Kinesis cost: ${kinesis_cost:.2f}/month',
                'recommendation': 'Switch from on-demand to provisioned shards if consistent throughput',
                'potential_savings': round(kinesis_cost * 0.25, 2),
                'priority': 'medium'
            })

        # CloudWatch Logs optimization
        logs_cost = cost_data['by_service'].get('Amazon CloudWatch', 0)
        if logs_cost > 20:
            recommendations.append({
                'service': 'CloudWatch Logs',
                'issue': f'High CloudWatch Logs cost: ${logs_cost:.2f}/month',
                'recommendation': 'Reduce log retention from 90 days to 30 days',
                'potential_savings': round(logs_cost * 0.67, 2),
                'priority': 'low'
            })

        return sorted(recommendations, key=lambda x: x['potential_savings'], reverse=True)

    def get_pipeline_cost(self, pipeline_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Calculate cost for a specific pipeline.

        Args:
            pipeline_id: Pipeline identifier
            days: Number of days to analyze

        Returns:
            Cost breakdown for pipeline
        """
        # Tag-based cost allocation (requires AWS Cost Allocation Tags)
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days)

        try:
            response = ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.isoformat(),
                    'End': end_date.isoformat()
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                Filter={
                    'Tags': {
                        'Key': 'streamforge:pipeline',
                        'Values': [pipeline_id]
                    }
                },
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
            )

            costs_by_service = {}
            total_cost = 0

            for result in response['ResultsByTime']:
                for group in result['Groups']:
                    service = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    costs_by_service[service] = cost
                    total_cost += cost

            return {
                'pipeline_id': pipeline_id,
                'total_cost': round(total_cost, 2),
                'by_service': costs_by_service,
                'days': days
            }

        except Exception as e:
            return {
                'pipeline_id': pipeline_id,
                'error': f'Cost tracking not available: {str(e)}',
                'note': 'Enable Cost Allocation Tags for per-pipeline cost tracking'
            }

    def forecast_cost(self, months: int = 3) -> Dict[str, Any]:
        """
        Forecast costs for next N months using AWS Cost Explorer forecasting.

        Args:
            months: Number of months to forecast

        Returns:
            Cost forecast
        """
        start_date = datetime.utcnow().date()
        end_date = start_date + timedelta(days=30 * months)

        response = ce.get_cost_forecast(
            TimePeriod={
                'Start': start_date.isoformat(),
                'End': end_date.isoformat()
            },
            Metric='UNBLENDED_COST',
            Granularity='MONTHLY'
        )

        forecast = []
        for result in response['ForecastResultsByTime']:
            forecast.append({
                'month': result['TimePeriod']['Start'][:7],  # YYYY-MM
                'forecast': round(float(result['MeanValue']), 2),
                'lower_bound': round(float(result['MeanValue']) * 0.8, 2),
                'upper_bound': round(float(result['MeanValue']) * 1.2, 2)
            })

        return {
            'forecast': forecast,
            'total_forecast': round(sum(f['forecast'] for f in forecast), 2)
        }

    def generate_cost_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive cost report with all insights.

        Returns:
            Complete cost analysis report
        """
        end_date = datetime.utcnow().date()
        start_date_month = end_date.replace(day=1)
        start_date_30d = end_date - timedelta(days=30)

        return {
            'generated_at': datetime.utcnow().isoformat(),
            'current_month': self.get_monthly_cost(
                start_date_month.isoformat(),
                end_date.isoformat()
            ),
            'last_30_days': self.get_monthly_cost(
                start_date_30d.isoformat(),
                end_date.isoformat()
            ),
            'trend': self.get_cost_trend(days=30),
            'anomalies': self.detect_cost_anomalies(),
            'recommendations': self.get_optimization_recommendations(),
            'forecast': self.forecast_cost(months=3)
        }


# Lambda handler
def lambda_handler(event, context):
    """
    AWS Lambda handler for cost analysis API.

    Endpoints:
    - GET /cost/report - Full cost report
    - GET /cost/trend - Cost trend
    - GET /cost/recommendations - Optimization recommendations
    - GET /cost/pipeline/{id} - Pipeline-specific costs
    """
    analyzer = CostAnalyzer()

    path = event.get('path', '')
    method = event.get('httpMethod', 'GET')

    if method != 'GET':
        return {'statusCode': 405, 'body': 'Method not allowed'}

    try:
        if path == '/cost/report':
            report = analyzer.generate_cost_report()
            return {
                'statusCode': 200,
                'body': json.dumps(report),
                'headers': {'Content-Type': 'application/json'}
            }

        elif path == '/cost/trend':
            days = int(event.get('queryStringParameters', {}).get('days', 30))
            trend = analyzer.get_cost_trend(days=days)
            return {
                'statusCode': 200,
                'body': json.dumps({'trend': trend}),
                'headers': {'Content-Type': 'application/json'}
            }

        elif path == '/cost/recommendations':
            recommendations = analyzer.get_optimization_recommendations()
            return {
                'statusCode': 200,
                'body': json.dumps({'recommendations': recommendations}),
                'headers': {'Content-Type': 'application/json'}
            }

        elif path.startswith('/cost/pipeline/'):
            pipeline_id = path.split('/')[-1]
            cost = analyzer.get_pipeline_cost(pipeline_id)
            return {
                'statusCode': 200,
                'body': json.dumps(cost),
                'headers': {'Content-Type': 'application/json'}
            }

        else:
            return {'statusCode': 404, 'body': 'Not found'}

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}),
            'headers': {'Content-Type': 'application/json'}
        }
