import * as cdk from 'aws-cdk-lib';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as subscriptions from 'aws-cdk-lib/aws-sns-subscriptions';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as kinesis from 'aws-cdk-lib/aws-kinesis';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import { Construct } from 'constructs';

interface MonitoringStackProps extends cdk.StackProps {
  ingestionStream: kinesis.Stream;
  pipelineStateMachine: sfn.StateMachine;
  runHistoryTable: dynamodb.Table;
  alertsTable: dynamodb.Table;
}

export class MonitoringStack extends cdk.Stack {
  public readonly alertTopic: sns.Topic;
  public readonly dashboard: cloudwatch.Dashboard;

  constructor(scope: Construct, id: string, props: MonitoringStackProps) {
    super(scope, id, props);

    // -----------------------------------------------------------------------
    // SNS Topic for Alerts
    // -----------------------------------------------------------------------
    this.alertTopic = new sns.Topic(this, 'AlertTopic', {
      topicName: 'streamforge-alerts',
      displayName: 'StreamForge Anomaly & System Alerts',
    });

    // Email subscription (parameterized via environment variable)
    const alertEmail = process.env.ALERT_EMAIL;
    if (alertEmail) {
      this.alertTopic.addSubscription(
        new subscriptions.EmailSubscription(alertEmail)
      );
    }

    // -----------------------------------------------------------------------
    // CloudWatch Dashboard
    // -----------------------------------------------------------------------
    this.dashboard = new cloudwatch.Dashboard(this, 'Dashboard', {
      dashboardName: 'StreamForge-Monitoring',
    });

    // Row 1: Ingestion Metrics
    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Kinesis Ingestion Rate',
        left: [
          props.ingestionStream.metricIncomingRecords({
            statistic: 'Sum',
            period: cdk.Duration.minutes(1),
          }),
          props.ingestionStream.metricIncomingBytes({
            statistic: 'Sum',
            period: cdk.Duration.minutes(1),
          }),
        ],
        width: 12,
      }),
      new cloudwatch.GraphWidget({
        title: 'Kinesis Throttling & Errors',
        left: [
          props.ingestionStream.metricWriteProvisionedThroughputExceeded({
            statistic: 'Sum',
            period: cdk.Duration.minutes(1),
          }),
        ],
        width: 12,
      })
    );

    // Row 2: Pipeline Processing Metrics
    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Step Functions Executions',
        left: [
          props.pipelineStateMachine.metricStarted({
            statistic: 'Sum',
            period: cdk.Duration.minutes(5),
          }),
          props.pipelineStateMachine.metricSucceeded({
            statistic: 'Sum',
            period: cdk.Duration.minutes(5),
          }),
          props.pipelineStateMachine.metricFailed({
            statistic: 'Sum',
            period: cdk.Duration.minutes(5),
          }),
        ],
        width: 12,
      }),
      new cloudwatch.GraphWidget({
        title: 'Pipeline Execution Duration',
        left: [
          props.pipelineStateMachine.metricTime({
            statistic: 'Average',
            period: cdk.Duration.minutes(5),
          }),
        ],
        width: 12,
      })
    );

    // Row 3: DynamoDB Metrics
    const runHistoryReadCapacity = props.runHistoryTable.metric('ConsumedReadCapacityUnits', {
      statistic: 'Sum',
      period: cdk.Duration.minutes(1),
    });
    const runHistoryWriteCapacity = props.runHistoryTable.metric('ConsumedWriteCapacityUnits', {
      statistic: 'Sum',
      period: cdk.Duration.minutes(1),
    });

    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'DynamoDB Run History - Consumed Capacity',
        left: [runHistoryReadCapacity, runHistoryWriteCapacity],
        width: 12,
      }),
      new cloudwatch.SingleValueWidget({
        title: 'Total Pipeline Runs (24h)',
        metrics: [
          props.runHistoryTable.metricUserErrors({
            statistic: 'SampleCount',
            period: cdk.Duration.hours(24),
          }),
        ],
        width: 12,
      })
    );

    // Row 4: Anomaly Detection Metrics
    const anomalyCountMetric = new cloudwatch.Metric({
      namespace: 'StreamForge',
      metricName: 'AnomaliesDetected',
      statistic: 'Sum',
      period: cdk.Duration.minutes(5),
    });

    const anomalyRateMetric = new cloudwatch.MathExpression({
      expression: '(anomalies / events) * 100',
      usingMetrics: {
        anomalies: anomalyCountMetric,
        events: new cloudwatch.Metric({
          namespace: 'StreamForge',
          metricName: 'EventsProcessed',
          statistic: 'Sum',
          period: cdk.Duration.minutes(5),
        }),
      },
      label: 'Anomaly Rate (%)',
    });

    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Anomalies Detected Over Time',
        left: [anomalyCountMetric],
        width: 12,
      }),
      new cloudwatch.GraphWidget({
        title: 'Anomaly Detection Rate (%)',
        left: [anomalyRateMetric],
        width: 12,
      })
    );

    // -----------------------------------------------------------------------
    // CloudWatch Alarms
    // -----------------------------------------------------------------------

    // Alarm: High Step Functions failure rate
    const pipelineFailureAlarm = new cloudwatch.Alarm(this, 'PipelineFailureAlarm', {
      alarmName: 'StreamForge-HighPipelineFailureRate',
      alarmDescription: 'Step Functions pipeline failure rate exceeds 10%',
      metric: new cloudwatch.MathExpression({
        expression: '(failures / (failures + successes)) * 100',
        usingMetrics: {
          failures: props.pipelineStateMachine.metricFailed({
            statistic: 'Sum',
            period: cdk.Duration.minutes(5),
          }),
          successes: props.pipelineStateMachine.metricSucceeded({
            statistic: 'Sum',
            period: cdk.Duration.minutes(5),
          }),
        },
      }),
      threshold: 10,
      evaluationPeriods: 2,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
    });
    pipelineFailureAlarm.addAlarmAction(new actions.SnsAction(this.alertTopic));

    // Alarm: High anomaly rate
    const highAnomalyAlarm = new cloudwatch.Alarm(this, 'HighAnomalyRateAlarm', {
      alarmName: 'StreamForge-HighAnomalyRate',
      alarmDescription: 'Anomaly detection rate exceeds 20% (potential data quality issue)',
      metric: anomalyRateMetric,
      threshold: 20,
      evaluationPeriods: 3,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    highAnomalyAlarm.addAlarmAction(new actions.SnsAction(this.alertTopic));

    // Alarm: Kinesis throttling
    const kinesisThrottlingAlarm = new cloudwatch.Alarm(this, 'KinesisThrottlingAlarm', {
      alarmName: 'StreamForge-KinesisThrottling',
      alarmDescription: 'Kinesis stream is being throttled',
      metric: props.ingestionStream.metricWriteProvisionedThroughputExceeded({
        statistic: 'Sum',
        period: cdk.Duration.minutes(1),
      }),
      threshold: 10,
      evaluationPeriods: 2,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
    });
    kinesisThrottlingAlarm.addAlarmAction(new actions.SnsAction(this.alertTopic));

    // Alarm: No data ingestion (dead pipeline)
    const noDataAlarm = new cloudwatch.Alarm(this, 'NoDataIngestionAlarm', {
      alarmName: 'StreamForge-NoDataIngestion',
      alarmDescription: 'No events ingested for 30 minutes',
      metric: props.ingestionStream.metricIncomingRecords({
        statistic: 'Sum',
        period: cdk.Duration.minutes(30),
      }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.BREACHING,
    });
    noDataAlarm.addAlarmAction(new actions.SnsAction(this.alertTopic));

    // -----------------------------------------------------------------------
    // Custom Metric Publisher Lambda
    // -----------------------------------------------------------------------
    const metricPublisher = new lambda.Function(this, 'MetricPublisher', {
      functionName: 'streamforge-metric-publisher',
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromInline(`
import json
import boto3
import os
from datetime import datetime

cloudwatch = boto3.client('cloudwatch')

def lambda_handler(event, context):
    """
    Triggered by DynamoDB Streams or EventBridge to publish custom metrics.
    Expected event: { "anomalies_detected": N, "events_processed": N, "pipeline_id": "..." }
    """

    try:
        # Parse metrics from event
        anomalies = event.get('anomalies_detected', 0)
        events = event.get('events_processed', 0)
        pipeline_id = event.get('pipeline_id', 'unknown')

        # Publish to CloudWatch
        cloudwatch.put_metric_data(
            Namespace='StreamForge',
            MetricData=[
                {
                    'MetricName': 'AnomaliesDetected',
                    'Value': anomalies,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow(),
                    'Dimensions': [
                        {'Name': 'PipelineId', 'Value': pipeline_id},
                    ],
                },
                {
                    'MetricName': 'EventsProcessed',
                    'Value': events,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow(),
                    'Dimensions': [
                        {'Name': 'PipelineId', 'Value': pipeline_id},
                    ],
                },
            ],
        )

        return {'statusCode': 200, 'body': 'Metrics published'}
    except Exception as e:
        print(f'Error publishing metrics: {e}')
        return {'statusCode': 500, 'body': str(e)}
      `),
      memorySize: 256,
      timeout: cdk.Duration.seconds(10),
    });

    // Grant CloudWatch PutMetricData permission
    metricPublisher.addToRolePolicy(
      new cdk.aws_iam.PolicyStatement({
        actions: ['cloudwatch:PutMetricData'],
        resources: ['*'],
      })
    );

    // -----------------------------------------------------------------------
    // Outputs
    // -----------------------------------------------------------------------
    new cdk.CfnOutput(this, 'DashboardUrl', {
      value: `https://console.aws.amazon.com/cloudwatch/home?region=${this.region}#dashboards:name=StreamForge-Monitoring`,
      description: 'CloudWatch Dashboard URL',
    });

    new cdk.CfnOutput(this, 'AlertTopicArn', {
      value: this.alertTopic.topicArn,
      description: 'SNS Topic ARN for alerts',
    });

    new cdk.CfnOutput(this, 'MetricPublisherArn', {
      value: metricPublisher.functionArn,
      description: 'Lambda function ARN for publishing custom metrics',
    });
  }
}
