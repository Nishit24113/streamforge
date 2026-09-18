import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as kinesis from 'aws-cdk-lib/aws-kinesis';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as path from 'path';
import { Construct } from 'constructs';

interface IngestionStackProps extends cdk.StackProps {
  dataLakeBucket: s3.Bucket;
  pipelineConfigTable: dynamodb.Table;
  runHistoryTable: dynamodb.Table;
}

export class IngestionStack extends cdk.Stack {
  public readonly api: apigateway.RestApi;
  public readonly ingestionStream: kinesis.Stream;

  constructor(scope: Construct, id: string, props: IngestionStackProps) {
    super(scope, id, props);

    // Kinesis Data Stream for real-time event ingestion
    this.ingestionStream = new kinesis.Stream(this, 'IngestionStream', {
      streamName: 'streamforge-events',
      streamMode: kinesis.StreamMode.ON_DEMAND,
      retentionPeriod: cdk.Duration.hours(24),
    });

    // Dead letter queue for failed events
    const dlq = new sqs.Queue(this, 'IngestionDLQ', {
      queueName: 'streamforge-ingestion-dlq',
      retentionPeriod: cdk.Duration.days(14),
    });

    // Shared Lambda layer for common dependencies
    const sharedLayer = new lambda.LayerVersion(this, 'SharedLayer', {
      layerVersionName: 'streamforge-shared',
      description: 'Shared utilities for StreamForge',
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_12],
      compatibleArchitectures: [lambda.Architecture.ARM_64],
      code: lambda.Code.fromAsset(path.join(__dirname, '../../services/shared'), {
        bundling: {
          image: lambda.Runtime.PYTHON_3_12.bundlingImage,
          platform: 'linux/arm64',
          command: [
            'bash', '-c',
            'pip install pyarrow pandas boto3 -t /asset-output/python && cp -r /asset-input/* /asset-output/python/',
          ],
        },
      }),
    });

    // API Handler — receives events via REST API
    const apiHandler = new lambda.Function(this, 'ApiHandler', {
      functionName: 'streamforge-api-handler',
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../services/ingestion/api-handler')),
      memorySize: 512,
      timeout: cdk.Duration.seconds(30),
      environment: {
        KINESIS_STREAM: this.ingestionStream.streamName,
        PIPELINE_TABLE: props.pipelineConfigTable.tableName,
        RUN_HISTORY_TABLE: props.runHistoryTable.tableName,
        DATA_LAKE_BUCKET: props.dataLakeBucket.bucketName,
        DLQ_URL: dlq.queueUrl,
      },
      layers: [sharedLayer],
    });

    this.ingestionStream.grantWrite(apiHandler);
    props.pipelineConfigTable.grantReadData(apiHandler);
    props.runHistoryTable.grantWriteData(apiHandler);
    props.dataLakeBucket.grantWrite(apiHandler);
    dlq.grantSendMessages(apiHandler);

    // Webhook Handler — processes inbound webhooks
    const webhookHandler = new lambda.Function(this, 'WebhookHandler', {
      functionName: 'streamforge-webhook-handler',
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../services/ingestion/webhook-handler')),
      memorySize: 256,
      timeout: cdk.Duration.seconds(30),
      environment: {
        KINESIS_STREAM: this.ingestionStream.streamName,
        PIPELINE_TABLE: props.pipelineConfigTable.tableName,
      },
    });

    this.ingestionStream.grantWrite(webhookHandler);
    props.pipelineConfigTable.grantReadData(webhookHandler);

    // File Processor — handles CSV/JSON uploads from S3
    const fileProcessor = new lambda.Function(this, 'FileProcessor', {
      functionName: 'streamforge-file-processor',
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../services/ingestion/file-processor')),
      memorySize: 1024,
      timeout: cdk.Duration.minutes(5),
      environment: {
        KINESIS_STREAM: this.ingestionStream.streamName,
        PIPELINE_TABLE: props.pipelineConfigTable.tableName,
        DATA_LAKE_BUCKET: props.dataLakeBucket.bucketName,
      },
      layers: [sharedLayer],
    });

    this.ingestionStream.grantWrite(fileProcessor);
    props.pipelineConfigTable.grantReadData(fileProcessor);
    props.dataLakeBucket.grantRead(fileProcessor);

    // API Gateway
    this.api = new apigateway.RestApi(this, 'StreamForgeApi', {
      restApiName: 'StreamForge API',
      description: 'StreamForge data pipeline ingestion API',
      deployOptions: {
        stageName: 'v1',
        throttlingRateLimit: 1000,
        throttlingBurstLimit: 2000,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'Authorization', 'X-Api-Key', 'X-Pipeline-Id'],
      },
    });

    // POST /ingest — send events to a pipeline
    const ingestResource = this.api.root.addResource('ingest');
    ingestResource.addMethod('POST', new apigateway.LambdaIntegration(apiHandler, {
      proxy: true,
    }));

    // POST /webhook/{pipeline_id} — receive webhooks
    const webhookResource = this.api.root.addResource('webhook');
    const webhookPipeline = webhookResource.addResource('{pipeline_id}');
    webhookPipeline.addMethod('POST', new apigateway.LambdaIntegration(webhookHandler, {
      proxy: true,
    }));

    // POST /upload — file upload (returns presigned URL)
    const uploadResource = this.api.root.addResource('upload');
    uploadResource.addMethod('POST', new apigateway.LambdaIntegration(apiHandler, {
      proxy: true,
    }));

    // GET /health
    const healthResource = this.api.root.addResource('health');
    healthResource.addMethod('GET', new apigateway.LambdaIntegration(apiHandler, {
      proxy: true,
    }));

    // GET /pipelines — list all pipelines
    const pipelinesResource = this.api.root.addResource('pipelines');
    pipelinesResource.addMethod('GET', new apigateway.LambdaIntegration(apiHandler, {
      proxy: true,
    }));

    // POST /pipelines — create a pipeline
    pipelinesResource.addMethod('POST', new apigateway.LambdaIntegration(apiHandler, {
      proxy: true,
    }));

    // GET /pipelines/{pipeline_id} — get pipeline details
    const pipelineDetail = pipelinesResource.addResource('{pipeline_id}');
    pipelineDetail.addMethod('GET', new apigateway.LambdaIntegration(apiHandler, {
      proxy: true,
    }));

    // GET /pipelines/{pipeline_id}/runs — get run history
    const runsResource = pipelineDetail.addResource('runs');
    runsResource.addMethod('GET', new apigateway.LambdaIntegration(apiHandler, {
      proxy: true,
    }));

    // Outputs
    new cdk.CfnOutput(this, 'ApiUrl', {
      value: this.api.url,
      description: 'StreamForge API URL',
    });

    new cdk.CfnOutput(this, 'StreamName', {
      value: this.ingestionStream.streamName,
      description: 'Kinesis stream name',
    });
  }
}
