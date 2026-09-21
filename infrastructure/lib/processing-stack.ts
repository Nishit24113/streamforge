import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as kinesis from 'aws-cdk-lib/aws-kinesis';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as eventsources from 'aws-cdk-lib/aws-lambda-event-sources';
import * as path from 'path';
import { Construct } from 'constructs';

interface ProcessingStackProps extends cdk.StackProps {
  dataLakeBucket: s3.Bucket;
  pipelineConfigTable: dynamodb.Table;
  runHistoryTable: dynamodb.Table;
  alertsTable: dynamodb.Table;
  ingestionStream: kinesis.Stream;
}

export class ProcessingStack extends cdk.Stack {
  public readonly pipelineStateMachine: sfn.StateMachine;

  constructor(scope: Construct, id: string, props: ProcessingStackProps) {
    super(scope, id, props);

    const commonEnv = {
      DATA_LAKE_BUCKET: props.dataLakeBucket.bucketName,
      PIPELINE_TABLE: props.pipelineConfigTable.tableName,
      RUN_HISTORY_TABLE: props.runHistoryTable.tableName,
      ALERTS_TABLE: props.alertsTable.tableName,
    };

    // Validator Lambda — schema validation and data quality
    const validator = new lambda.Function(this, 'Validator', {
      functionName: 'streamforge-validator',
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../services/processing/validator')),
      memorySize: 512,
      timeout: cdk.Duration.seconds(60),
      environment: commonEnv,
    });

    // Transformer Lambda — apply transformation rules
    const transformer = new lambda.Function(this, 'Transformer', {
      functionName: 'streamforge-transformer',
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../services/processing/transformer')),
      memorySize: 1024,
      timeout: cdk.Duration.minutes(2),
      environment: commonEnv,
    });

    // Aggregator Lambda — window-based aggregations
    const aggregator = new lambda.Function(this, 'Aggregator', {
      functionName: 'streamforge-aggregator',
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../services/processing/aggregator')),
      memorySize: 1024,
      timeout: cdk.Duration.minutes(3),
      environment: commonEnv,
    });

    // Anomaly Detector Lambda — ML-based anomaly detection
    const anomalyDetector = new lambda.Function(this, 'AnomalyDetector', {
      functionName: 'streamforge-anomaly-detector',
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../services/processing/anomaly-detector')),
      memorySize: 1024,
      timeout: cdk.Duration.minutes(3),
      environment: commonEnv,
    });

    // Grant permissions to all processing Lambdas
    [validator, transformer, aggregator, anomalyDetector].forEach(fn => {
      props.dataLakeBucket.grantReadWrite(fn);
      props.pipelineConfigTable.grantReadData(fn);
      props.runHistoryTable.grantReadWriteData(fn);
      props.alertsTable.grantWriteData(fn);
    });

    // Step Functions Pipeline — orchestrates the processing flow
    const validateStep = new tasks.LambdaInvoke(this, 'ValidateEvents', {
      lambdaFunction: validator,
      outputPath: '$.Payload',
      retryOnServiceExceptions: true,
    });

    const transformStep = new tasks.LambdaInvoke(this, 'TransformEvents', {
      lambdaFunction: transformer,
      outputPath: '$.Payload',
      retryOnServiceExceptions: true,
    });

    const detectAnomaliesStep = new tasks.LambdaInvoke(this, 'DetectAnomalies', {
      lambdaFunction: anomalyDetector,
      outputPath: '$.Payload',
      retryOnServiceExceptions: true,
    });

    const aggregateStep = new tasks.LambdaInvoke(this, 'AggregateEvents', {
      lambdaFunction: aggregator,
      outputPath: '$.Payload',
      retryOnServiceExceptions: true,
    });

    const aggregateStepAlt = new tasks.LambdaInvoke(this, 'AggregateEventsAlt', {
      lambdaFunction: aggregator,
      outputPath: '$.Payload',
      retryOnServiceExceptions: true,
    });

    const hasAnomalyDetection = sfn.Condition.booleanEquals('$.pipeline_config.detect_anomalies', true);
    const hasAggregation = sfn.Condition.booleanEquals('$.pipeline_config.aggregate', true);

    const recordSuccess = new sfn.Pass(this, 'RecordSuccess', {
      parameters: {
        'status': 'COMPLETED',
        'pipeline_id.$': '$.pipeline_id',
        'run_id.$': '$.run_id',
        'events_processed.$': '$.events_processed',
        'anomalies_detected.$': '$.anomalies_detected',
      },
    });

    const recordSuccessNoAnomalies = new sfn.Pass(this, 'RecordSuccessNoAnomalies', {
      parameters: {
        'status': 'COMPLETED',
        'pipeline_id.$': '$.pipeline_id',
        'run_id.$': '$.run_id',
        'events_processed.$': '$.events_processed',
        'anomalies_detected': 0,
      },
    });

    const recordFailure = new sfn.Pass(this, 'RecordFailure', {
      parameters: {
        'status': 'FAILED',
        'pipeline_id.$': '$.pipeline_id',
        'run_id.$': '$.run_id',
        'error.$': '$.error',
      },
    });

    const anomalyChoice = new sfn.Choice(this, 'NeedAnomalyDetection?')
      .when(hasAnomalyDetection, detectAnomaliesStep.next(
        new sfn.Choice(this, 'NeedAggregation?')
          .when(hasAggregation, aggregateStep.next(recordSuccess))
          .otherwise(recordSuccess)
      ))
      .otherwise(
        new sfn.Choice(this, 'NeedAggregationOnly?')
          .when(hasAggregation, aggregateStepAlt.next(recordSuccessNoAnomalies))
          .otherwise(recordSuccessNoAnomalies)
      );

    const definition = validateStep
      .addCatch(recordFailure, { errors: ['States.ALL'] })
      .next(transformStep.addCatch(recordFailure, { errors: ['States.ALL'] }))
      .next(anomalyChoice);

    this.pipelineStateMachine = new sfn.StateMachine(this, 'PipelineStateMachine', {
      stateMachineName: 'streamforge-pipeline',
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      timeout: cdk.Duration.minutes(15),
      tracingEnabled: true,
    });

    // Stream Processor — reads from Kinesis, triggers Step Functions
    const streamProcessor = new lambda.Function(this, 'StreamProcessor', {
      functionName: 'streamforge-stream-processor',
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../services/processing/stream-processor')),
      memorySize: 512,
      timeout: cdk.Duration.minutes(2),
      environment: {
        ...commonEnv,
        STATE_MACHINE_ARN: this.pipelineStateMachine.stateMachineArn,
      },
    });

    this.pipelineStateMachine.grantStartExecution(streamProcessor);
    props.pipelineConfigTable.grantReadData(streamProcessor);
    props.runHistoryTable.grantWriteData(streamProcessor);
    props.dataLakeBucket.grantWrite(streamProcessor);

    // Kinesis event source — batch processing with parallelization
    streamProcessor.addEventSource(new eventsources.KinesisEventSource(props.ingestionStream, {
      batchSize: 100,
      startingPosition: lambda.StartingPosition.TRIM_HORIZON,
      maxBatchingWindow: cdk.Duration.seconds(30),
      parallelizationFactor: 2,
      retryAttempts: 3,
      bisectBatchOnError: true,
    }));

    // Outputs
    new cdk.CfnOutput(this, 'StateMachineArn', {
      value: this.pipelineStateMachine.stateMachineArn,
      description: 'Pipeline state machine ARN',
    });
  }
}
