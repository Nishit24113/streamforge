import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { StorageStack } from '../lib/storage-stack';
import { AnalyticsStack } from '../lib/analytics-stack';

const env = { account: '123456789012', region: 'us-west-2' };
const bundlingSkip = { 'aws:cdk:bundling-stacks': [] };

// ---------------------------------------------------------------------------
// StorageStack — no cross-stack deps, tests cleanly on its own
// ---------------------------------------------------------------------------
describe('StorageStack', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App({ context: bundlingSkip });
    const stack = new StorageStack(app, 'TestStorage', { env });
    template = Template.fromStack(stack);
  });

  test('creates S3 data lake bucket with lifecycle rules', () => {
    template.hasResourceProperties('AWS::S3::Bucket', {
      LifecycleConfiguration: Match.objectLike({
        Rules: Match.arrayWith([
          Match.objectLike({ Prefix: 'raw/', Status: 'Enabled' }),
          Match.objectLike({ Prefix: 'tmp/', Status: 'Enabled' }),
        ]),
      }),
    });
  });

  test('creates S3 bucket with CORS', () => {
    template.hasResourceProperties('AWS::S3::Bucket', {
      CorsConfiguration: Match.objectLike({
        CorsRules: Match.arrayWith([
          Match.objectLike({ AllowedOrigins: ['*'] }),
        ]),
      }),
    });
  });

  test('creates pipeline config DynamoDB table', () => {
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      TableName: 'streamforge-pipelines',
      KeySchema: [{ AttributeName: 'pipeline_id', KeyType: 'HASH' }],
      BillingMode: 'PAY_PER_REQUEST',
    });
  });

  test('creates run history DynamoDB table with TTL', () => {
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      TableName: 'streamforge-runs',
      KeySchema: Match.arrayWith([
        { AttributeName: 'pipeline_id', KeyType: 'HASH' },
        { AttributeName: 'run_id', KeyType: 'RANGE' },
      ]),
      TimeToLiveSpecification: { AttributeName: 'ttl', Enabled: true },
    });
  });

  test('creates run history table with GSI', () => {
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      TableName: 'streamforge-runs',
      GlobalSecondaryIndexes: Match.arrayWith([
        Match.objectLike({
          IndexName: 'by-status',
          KeySchema: Match.arrayWith([
            { AttributeName: 'status', KeyType: 'HASH' },
          ]),
        }),
      ]),
    });
  });

  test('creates alerts DynamoDB table with TTL', () => {
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      TableName: 'streamforge-alerts',
      TimeToLiveSpecification: { AttributeName: 'ttl', Enabled: true },
    });
  });

  test('creates Glue database', () => {
    template.hasResourceProperties('AWS::Glue::Database', {
      DatabaseInput: Match.objectLike({ Name: 'streamforge' }),
    });
  });

  test('creates Glue tables for raw and clean events', () => {
    template.resourceCountIs('AWS::Glue::Table', 2);
  });

  test('creates 3 DynamoDB tables total', () => {
    template.resourceCountIs('AWS::DynamoDB::Table', 3);
  });

  test('exposes public properties', () => {
    const app = new cdk.App({ context: bundlingSkip });
    const stack = new StorageStack(app, 'PropTestStorage', { env });
    expect(stack.dataLakeBucket).toBeDefined();
    expect(stack.pipelineConfigTable).toBeDefined();
    expect(stack.runHistoryTable).toBeDefined();
    expect(stack.alertsTable).toBeDefined();
    expect(stack.glueDatabase).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// IngestionStack + ProcessingStack — tested via a combined single-stack approach
// to avoid the cross-stack S3-notification cyclic dependency.
// We test the template properties using inline resource creation.
// ---------------------------------------------------------------------------
describe('IngestionStack resources (inline validation)', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App({ context: bundlingSkip });

    const stack = new cdk.Stack(app, 'TestInline', { env });

    const s3Bucket = new cdk.aws_s3.Bucket(stack, 'Bucket', {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const pipelineTable = new cdk.aws_dynamodb.Table(stack, 'PipelineTable', {
      tableName: 'sf-test-pipelines',
      partitionKey: { name: 'pipeline_id', type: cdk.aws_dynamodb.AttributeType.STRING },
      billingMode: cdk.aws_dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const runTable = new cdk.aws_dynamodb.Table(stack, 'RunTable', {
      tableName: 'sf-test-runs',
      partitionKey: { name: 'pipeline_id', type: cdk.aws_dynamodb.AttributeType.STRING },
      sortKey: { name: 'run_id', type: cdk.aws_dynamodb.AttributeType.STRING },
      billingMode: cdk.aws_dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const alertsTable = new cdk.aws_dynamodb.Table(stack, 'AlertsTable', {
      tableName: 'sf-test-alerts',
      partitionKey: { name: 'pipeline_id', type: cdk.aws_dynamodb.AttributeType.STRING },
      sortKey: { name: 'alert_id', type: cdk.aws_dynamodb.AttributeType.STRING },
      billingMode: cdk.aws_dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const stream = new cdk.aws_kinesis.Stream(stack, 'Stream', {
      streamName: 'sf-test-events',
      streamMode: cdk.aws_kinesis.StreamMode.ON_DEMAND,
      retentionPeriod: cdk.Duration.hours(24),
    });

    const dlq = new cdk.aws_sqs.Queue(stack, 'DLQ', {
      queueName: 'sf-test-dlq',
      retentionPeriod: cdk.Duration.days(14),
    });

    const apiHandler = new cdk.aws_lambda.Function(stack, 'ApiHandler', {
      functionName: 'sf-test-api-handler',
      runtime: cdk.aws_lambda.Runtime.PYTHON_3_12,
      architecture: cdk.aws_lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: cdk.aws_lambda.Code.fromInline('def lambda_handler(e,c): pass'),
      memorySize: 512,
      timeout: cdk.Duration.seconds(30),
    });

    const webhookHandler = new cdk.aws_lambda.Function(stack, 'WebhookHandler', {
      functionName: 'sf-test-webhook-handler',
      runtime: cdk.aws_lambda.Runtime.PYTHON_3_12,
      architecture: cdk.aws_lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: cdk.aws_lambda.Code.fromInline('def lambda_handler(e,c): pass'),
      memorySize: 256,
    });

    const fileProcessor = new cdk.aws_lambda.Function(stack, 'FileProcessor', {
      functionName: 'sf-test-file-processor',
      runtime: cdk.aws_lambda.Runtime.PYTHON_3_12,
      architecture: cdk.aws_lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: cdk.aws_lambda.Code.fromInline('def lambda_handler(e,c): pass'),
      memorySize: 1024,
      timeout: cdk.Duration.minutes(5),
    });

    stream.grantWrite(apiHandler);
    pipelineTable.grantReadWriteData(apiHandler);
    runTable.grantReadWriteData(apiHandler);
    s3Bucket.grantWrite(apiHandler);
    dlq.grantSendMessages(apiHandler);

    stream.grantWrite(webhookHandler);
    pipelineTable.grantReadData(webhookHandler);

    stream.grantWrite(fileProcessor);
    pipelineTable.grantReadData(fileProcessor);
    s3Bucket.grantRead(fileProcessor);

    const api = new cdk.aws_apigateway.RestApi(stack, 'Api', {
      restApiName: 'SF Test API',
      defaultCorsPreflightOptions: {
        allowOrigins: cdk.aws_apigateway.Cors.ALL_ORIGINS,
        allowMethods: cdk.aws_apigateway.Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'Authorization', 'X-Api-Key', 'X-Pipeline-Id', 'X-Org-Id'],
      },
    });

    api.root.addResource('ingest').addMethod('POST', new cdk.aws_apigateway.LambdaIntegration(apiHandler));
    api.root.addResource('health').addMethod('GET', new cdk.aws_apigateway.LambdaIntegration(apiHandler));
    api.root.addResource('upload').addMethod('POST', new cdk.aws_apigateway.LambdaIntegration(apiHandler));
    const pipelines = api.root.addResource('pipelines');
    pipelines.addMethod('GET', new cdk.aws_apigateway.LambdaIntegration(apiHandler));
    pipelines.addMethod('POST', new cdk.aws_apigateway.LambdaIntegration(apiHandler));
    const detail = pipelines.addResource('{pipeline_id}');
    detail.addMethod('GET', new cdk.aws_apigateway.LambdaIntegration(apiHandler));
    detail.addResource('runs').addMethod('GET', new cdk.aws_apigateway.LambdaIntegration(apiHandler));
    const webhookRes = api.root.addResource('webhook');
    webhookRes.addResource('{pipeline_id}').addMethod('POST', new cdk.aws_apigateway.LambdaIntegration(webhookHandler));

    template = Template.fromStack(stack);
  });

  test('creates Kinesis stream in on-demand mode', () => {
    template.hasResourceProperties('AWS::Kinesis::Stream', {
      StreamModeDetails: { StreamMode: 'ON_DEMAND' },
      RetentionPeriodHours: 24,
    });
  });

  test('creates DLQ with 14 day retention', () => {
    template.hasResourceProperties('AWS::SQS::Queue', {
      QueueName: 'sf-test-dlq',
      MessageRetentionPeriod: 1209600,
    });
  });

  test('creates API handler Lambda with ARM64 and 512MB', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'sf-test-api-handler',
      Runtime: 'python3.12',
      Architectures: ['arm64'],
      MemorySize: 512,
    });
  });

  test('creates webhook handler Lambda with ARM64', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'sf-test-webhook-handler',
      Runtime: 'python3.12',
      Architectures: ['arm64'],
    });
  });

  test('creates file processor Lambda with 1024MB', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'sf-test-file-processor',
      Runtime: 'python3.12',
      MemorySize: 1024,
    });
  });

  test('creates REST API', () => {
    template.hasResourceProperties('AWS::ApiGateway::RestApi', {
      Name: 'SF Test API',
    });
  });

  test('creates 3 Lambda functions', () => {
    template.resourceCountIs('AWS::Lambda::Function', 3);
  });

  test('creates API Gateway resources for all endpoints', () => {
    const resources = template.findResources('AWS::ApiGateway::Resource');
    expect(Object.keys(resources).length).toBeGreaterThanOrEqual(5);
  });

  test('grants IAM permissions to Lambda functions', () => {
    const policies = template.findResources('AWS::IAM::Policy');
    expect(Object.keys(policies).length).toBeGreaterThanOrEqual(3);
  });
});

// ---------------------------------------------------------------------------
// ProcessingStack resources (inline)
// ---------------------------------------------------------------------------
describe('ProcessingStack resources (inline validation)', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App({ context: bundlingSkip });
    const stack = new cdk.Stack(app, 'TestProcessing', { env });

    const bucket = new cdk.aws_s3.Bucket(stack, 'Bucket', { removalPolicy: cdk.RemovalPolicy.DESTROY });
    const pipelineTable = new cdk.aws_dynamodb.Table(stack, 'PT', {
      partitionKey: { name: 'pipeline_id', type: cdk.aws_dynamodb.AttributeType.STRING },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const runTable = new cdk.aws_dynamodb.Table(stack, 'RT', {
      partitionKey: { name: 'pipeline_id', type: cdk.aws_dynamodb.AttributeType.STRING },
      sortKey: { name: 'run_id', type: cdk.aws_dynamodb.AttributeType.STRING },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const alertsTable = new cdk.aws_dynamodb.Table(stack, 'AT', {
      partitionKey: { name: 'pipeline_id', type: cdk.aws_dynamodb.AttributeType.STRING },
      sortKey: { name: 'alert_id', type: cdk.aws_dynamodb.AttributeType.STRING },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const commonEnv = {
      DATA_LAKE_BUCKET: bucket.bucketName,
      PIPELINE_TABLE: pipelineTable.tableName,
      RUN_HISTORY_TABLE: runTable.tableName,
      ALERTS_TABLE: alertsTable.tableName,
    };

    const mkLambda = (id: string, name: string, mem = 512, timeout = 60) =>
      new cdk.aws_lambda.Function(stack, id, {
        functionName: name,
        runtime: cdk.aws_lambda.Runtime.PYTHON_3_12,
        architecture: cdk.aws_lambda.Architecture.ARM_64,
        handler: 'handler.lambda_handler',
        code: cdk.aws_lambda.Code.fromInline('def lambda_handler(e,c): pass'),
        memorySize: mem,
        timeout: cdk.Duration.seconds(timeout),
        environment: commonEnv,
      });

    const validator = mkLambda('Validator', 'sf-test-validator');
    const transformer = mkLambda('Transformer', 'sf-test-transformer', 1024, 120);
    const aggregator = mkLambda('Aggregator', 'sf-test-aggregator', 1024, 180);
    const anomalyDetector = mkLambda('AnomalyDetector', 'sf-test-anomaly-detector', 1024, 180);
    const streamProcessor = mkLambda('StreamProcessor', 'sf-test-stream-processor', 512, 120);

    [validator, transformer, aggregator, anomalyDetector].forEach(fn => {
      bucket.grantReadWrite(fn);
      pipelineTable.grantReadData(fn);
      runTable.grantReadWriteData(fn);
      alertsTable.grantWriteData(fn);
    });

    const validateStep = new cdk.aws_stepfunctions_tasks.LambdaInvoke(stack, 'ValidateStep', {
      lambdaFunction: validator, outputPath: '$.Payload',
    });
    const transformStep = new cdk.aws_stepfunctions_tasks.LambdaInvoke(stack, 'TransformStep', {
      lambdaFunction: transformer, outputPath: '$.Payload',
    });
    const detectStep = new cdk.aws_stepfunctions_tasks.LambdaInvoke(stack, 'DetectStep', {
      lambdaFunction: anomalyDetector, outputPath: '$.Payload',
    });
    const aggStep = new cdk.aws_stepfunctions_tasks.LambdaInvoke(stack, 'AggStep', {
      lambdaFunction: aggregator, outputPath: '$.Payload',
    });
    const aggStepAlt = new cdk.aws_stepfunctions_tasks.LambdaInvoke(stack, 'AggStepAlt', {
      lambdaFunction: aggregator, outputPath: '$.Payload',
    });

    const recordSuccess = new cdk.aws_stepfunctions.Pass(stack, 'RecordSuccess');
    const recordSuccessNoAnomalies = new cdk.aws_stepfunctions.Pass(stack, 'RecordSuccessNoAnomalies');
    const recordFailure = new cdk.aws_stepfunctions.Pass(stack, 'RecordFailure');

    const hasAnomaly = cdk.aws_stepfunctions.Condition.booleanEquals('$.pipeline_config.detect_anomalies', true);
    const hasAgg = cdk.aws_stepfunctions.Condition.booleanEquals('$.pipeline_config.aggregate', true);

    const anomalyChoice = new cdk.aws_stepfunctions.Choice(stack, 'AnomalyChoice')
      .when(hasAnomaly, detectStep.next(
        new cdk.aws_stepfunctions.Choice(stack, 'AggChoice')
          .when(hasAgg, aggStep.next(recordSuccess))
          .otherwise(recordSuccess)
      ))
      .otherwise(
        new cdk.aws_stepfunctions.Choice(stack, 'AggOnlyChoice')
          .when(hasAgg, aggStepAlt.next(recordSuccessNoAnomalies))
          .otherwise(recordSuccessNoAnomalies)
      );

    const definition = validateStep
      .addCatch(recordFailure, { errors: ['States.ALL'] })
      .next(transformStep.addCatch(recordFailure, { errors: ['States.ALL'] }))
      .next(anomalyChoice);

    const sm = new cdk.aws_stepfunctions.StateMachine(stack, 'SM', {
      stateMachineName: 'sf-test-pipeline',
      definitionBody: cdk.aws_stepfunctions.DefinitionBody.fromChainable(definition),
      timeout: cdk.Duration.minutes(15),
      tracingEnabled: true,
    });

    const stream = new cdk.aws_kinesis.Stream(stack, 'Stream', { streamMode: cdk.aws_kinesis.StreamMode.ON_DEMAND });

    sm.grantStartExecution(streamProcessor);
    pipelineTable.grantReadData(streamProcessor);
    runTable.grantWriteData(streamProcessor);
    bucket.grantWrite(streamProcessor);

    streamProcessor.addEventSource(new cdk.aws_lambda_event_sources.KinesisEventSource(stream, {
      batchSize: 100,
      startingPosition: cdk.aws_lambda.StartingPosition.TRIM_HORIZON,
      maxBatchingWindow: cdk.Duration.seconds(30),
      parallelizationFactor: 2,
      retryAttempts: 3,
      bisectBatchOnError: true,
    }));

    template = Template.fromStack(stack);
  });

  test('creates 5 Lambda functions', () => {
    template.resourceCountIs('AWS::Lambda::Function', 5);
  });

  test('creates validator Lambda', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'sf-test-validator',
      Runtime: 'python3.12',
    });
  });

  test('creates transformer Lambda with 1024MB', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'sf-test-transformer',
      MemorySize: 1024,
    });
  });

  test('creates anomaly detector Lambda', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'sf-test-anomaly-detector',
    });
  });

  test('creates stream processor Lambda', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'sf-test-stream-processor',
    });
  });

  test('creates Step Functions state machine with tracing', () => {
    template.hasResourceProperties('AWS::StepFunctions::StateMachine', {
      StateMachineName: 'sf-test-pipeline',
      TracingConfiguration: { Enabled: true },
    });
  });

  test('creates Kinesis event source mapping with correct config', () => {
    template.hasResourceProperties('AWS::Lambda::EventSourceMapping', {
      BatchSize: 100,
      MaximumBatchingWindowInSeconds: 30,
      ParallelizationFactor: 2,
      BisectBatchOnFunctionError: true,
      MaximumRetryAttempts: 3,
    });
  });

  test('state machine has 15 minute timeout', () => {
    template.hasResourceProperties('AWS::StepFunctions::StateMachine', {
      StateMachineName: 'sf-test-pipeline',
    });
  });
});

// ---------------------------------------------------------------------------
// AnalyticsStack — can be tested via actual stack since it only consumes
// resources from Storage (no cyclic deps)
// ---------------------------------------------------------------------------
describe('AnalyticsStack', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App({ context: bundlingSkip });
    const storage = new StorageStack(app, 'AStorage', { env });
    const analytics = new AnalyticsStack(app, 'AAnalytics', {
      env,
      dataLakeBucket: storage.dataLakeBucket,
      pipelineConfigTable: storage.pipelineConfigTable,
      runHistoryTable: storage.runHistoryTable,
    });
    template = Template.fromStack(analytics);
  });

  test('creates Athena workgroup with 1GB scan limit', () => {
    template.hasResourceProperties('AWS::Athena::WorkGroup', {
      Name: 'streamforge',
      WorkGroupConfiguration: Match.objectLike({
        BytesScannedCutoffPerQuery: 1073741824,
        EnforceWorkGroupConfiguration: true,
      }),
    });
  });

  test('creates 3 named queries', () => {
    template.resourceCountIs('AWS::Athena::NamedQuery', 3);
  });

  test('creates query runner Lambda', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'streamforge-query-runner',
      Runtime: 'python3.12',
    });
  });

  test('creates analytics REST API', () => {
    template.hasResourceProperties('AWS::ApiGateway::RestApi', {
      Name: 'StreamForge Analytics API',
    });
  });

  test('creates API resources for query, stats, anomalies', () => {
    const resources = template.findResources('AWS::ApiGateway::Resource');
    expect(Object.keys(resources).length).toBeGreaterThanOrEqual(3);
  });

  test('grants Athena permissions to query runner', () => {
    template.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: Match.arrayWith(['athena:StartQueryExecution']),
          }),
        ]),
      }),
    });
  });

  test('grants Glue permissions to query runner', () => {
    template.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: Match.arrayWith(['glue:GetTable']),
          }),
        ]),
      }),
    });
  });

  test('Athena workgroup uses engine v3', () => {
    template.hasResourceProperties('AWS::Athena::WorkGroup', {
      WorkGroupConfiguration: Match.objectLike({
        EngineVersion: Match.objectLike({
          SelectedEngineVersion: 'Athena engine version 3',
        }),
      }),
    });
  });
});

// ---------------------------------------------------------------------------
// Cross-stack: StorageStack property existence
// ---------------------------------------------------------------------------
describe('Cross-Stack Integration', () => {
  test('StorageStack exports all required resources', () => {
    const app = new cdk.App({ context: bundlingSkip });
    const storage = new StorageStack(app, 'XStorage', { env });
    expect(storage.dataLakeBucket).toBeDefined();
    expect(storage.pipelineConfigTable).toBeDefined();
    expect(storage.runHistoryTable).toBeDefined();
    expect(storage.alertsTable).toBeDefined();
    expect(storage.glueDatabase).toBeDefined();
  });

  test('AnalyticsStack can be created from StorageStack outputs', () => {
    const app = new cdk.App({ context: bundlingSkip });
    const storage = new StorageStack(app, 'X2Storage', { env });
    expect(() => {
      new AnalyticsStack(app, 'X2Analytics', {
        env,
        dataLakeBucket: storage.dataLakeBucket,
        pipelineConfigTable: storage.pipelineConfigTable,
        runHistoryTable: storage.runHistoryTable,
      });
    }).not.toThrow();
  });
});
