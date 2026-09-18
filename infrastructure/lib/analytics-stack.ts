import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as athena from 'aws-cdk-lib/aws-athena';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as path from 'path';
import { Construct } from 'constructs';

interface AnalyticsStackProps extends cdk.StackProps {
  dataLakeBucket: s3.Bucket;
  pipelineConfigTable: dynamodb.Table;
  runHistoryTable: dynamodb.Table;
}

export class AnalyticsStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: AnalyticsStackProps) {
    super(scope, id, props);

    // Athena workgroup with cost controls
    const workgroup = new athena.CfnWorkGroup(this, 'AthenaWorkgroup', {
      name: 'streamforge',
      description: 'StreamForge analytics workgroup',
      state: 'ENABLED',
      workGroupConfiguration: {
        resultConfiguration: {
          outputLocation: `s3://${props.dataLakeBucket.bucketName}/athena-results/`,
          encryptionConfiguration: {
            encryptionOption: 'SSE_S3',
          },
        },
        enforceWorkGroupConfiguration: true,
        bytesScannedCutoffPerQuery: 1073741824, // 1 GB limit per query
        publishCloudWatchMetricsEnabled: true,
        engineVersion: {
          selectedEngineVersion: 'Athena engine version 3',
        },
      },
    });

    // Pre-built named queries
    new athena.CfnNamedQuery(this, 'EventCountByType', {
      name: 'event-count-by-type',
      database: 'streamforge',
      workGroup: 'streamforge',
      description: 'Count events grouped by type for the last 7 days',
      queryString: `
        SELECT event_type, COUNT(*) as event_count,
               DATE(from_unixtime(timestamp/1000)) as event_date
        FROM streamforge.clean_events
        WHERE year = CAST(year(current_date) AS VARCHAR)
          AND month = LPAD(CAST(month(current_date) AS VARCHAR), 2, '0')
        GROUP BY event_type, DATE(from_unixtime(timestamp/1000))
        ORDER BY event_date DESC, event_count DESC
      `,
    });

    new athena.CfnNamedQuery(this, 'AnomalySummary', {
      name: 'anomaly-summary',
      database: 'streamforge',
      workGroup: 'streamforge',
      description: 'Summary of detected anomalies',
      queryString: `
        SELECT event_type,
               COUNT(*) as total_events,
               SUM(CASE WHEN is_anomaly THEN 1 ELSE 0 END) as anomaly_count,
               ROUND(AVG(anomaly_score), 4) as avg_anomaly_score,
               ROUND(100.0 * SUM(CASE WHEN is_anomaly THEN 1 ELSE 0 END) / COUNT(*), 2) as anomaly_pct
        FROM streamforge.clean_events
        WHERE is_anomaly IS NOT NULL
        GROUP BY event_type
        ORDER BY anomaly_count DESC
      `,
    });

    new athena.CfnNamedQuery(this, 'HourlyThroughput', {
      name: 'hourly-throughput',
      database: 'streamforge',
      workGroup: 'streamforge',
      description: 'Hourly event throughput for the last 24 hours',
      queryString: `
        SELECT DATE_FORMAT(from_unixtime(timestamp/1000), '%Y-%m-%d %H:00') as hour,
               pipeline_id,
               COUNT(*) as events,
               COUNT(DISTINCT source) as unique_sources
        FROM streamforge.raw_events
        WHERE timestamp > (to_unixtime(current_timestamp) - 86400) * 1000
        GROUP BY DATE_FORMAT(from_unixtime(timestamp/1000), '%Y-%m-%d %H:00'), pipeline_id
        ORDER BY hour DESC
      `,
    });

    // Query Runner Lambda
    const queryRunner = new lambda.Function(this, 'QueryRunner', {
      functionName: 'streamforge-query-runner',
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../services/analytics/query-runner')),
      memorySize: 512,
      timeout: cdk.Duration.seconds(60),
      environment: {
        DATA_LAKE_BUCKET: props.dataLakeBucket.bucketName,
        ATHENA_WORKGROUP: 'streamforge',
        ATHENA_DATABASE: 'streamforge',
        PIPELINE_TABLE: props.pipelineConfigTable.tableName,
        RUN_HISTORY_TABLE: props.runHistoryTable.tableName,
      },
    });

    props.dataLakeBucket.grantReadWrite(queryRunner);
    props.pipelineConfigTable.grantReadData(queryRunner);
    props.runHistoryTable.grantReadData(queryRunner);

    queryRunner.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'athena:StartQueryExecution',
        'athena:GetQueryExecution',
        'athena:GetQueryResults',
        'athena:StopQueryExecution',
        'athena:ListNamedQueries',
        'athena:GetNamedQuery',
      ],
      resources: ['*'],
    }));

    queryRunner.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'glue:GetTable',
        'glue:GetTables',
        'glue:GetDatabase',
        'glue:GetDatabases',
        'glue:GetPartitions',
      ],
      resources: ['*'],
    }));

    // Analytics API Gateway
    const analyticsApi = new apigateway.RestApi(this, 'AnalyticsApi', {
      restApiName: 'StreamForge Analytics API',
      description: 'Query and analytics endpoints',
      deployOptions: {
        stageName: 'v1',
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'Authorization'],
      },
    });

    // POST /query — run SQL query
    const queryResource = analyticsApi.root.addResource('query');
    queryResource.addMethod('POST', new apigateway.LambdaIntegration(queryRunner));

    // GET /query/{query_id} — get query results
    const queryDetail = queryResource.addResource('{query_id}');
    queryDetail.addMethod('GET', new apigateway.LambdaIntegration(queryRunner));

    // GET /stats — pipeline statistics
    const statsResource = analyticsApi.root.addResource('stats');
    statsResource.addMethod('GET', new apigateway.LambdaIntegration(queryRunner));

    // GET /anomalies — anomaly timeline
    const anomaliesResource = analyticsApi.root.addResource('anomalies');
    anomaliesResource.addMethod('GET', new apigateway.LambdaIntegration(queryRunner));

    // Outputs
    new cdk.CfnOutput(this, 'AnalyticsApiUrl', {
      value: analyticsApi.url,
      description: 'Analytics API URL',
    });

    new cdk.CfnOutput(this, 'AthenaWorkgroupName', {
      value: 'streamforge',
      description: 'Athena workgroup',
    });
  }
}
