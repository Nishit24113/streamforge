import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as glue from 'aws-cdk-lib/aws-glue';
import { Construct } from 'constructs';

export class StorageStack extends cdk.Stack {
  public readonly dataLakeBucket: s3.Bucket;
  public readonly pipelineConfigTable: dynamodb.Table;
  public readonly runHistoryTable: dynamodb.Table;
  public readonly alertsTable: dynamodb.Table;
  public readonly glueDatabase: glue.CfnDatabase;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // S3 Data Lake — three-zone architecture (raw/clean/agg)
    this.dataLakeBucket = new s3.Bucket(this, 'DataLakeBucket', {
      bucketName: `streamforge-lake-${this.account}-${this.region}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: false,
      encryption: s3.BucketEncryption.S3_MANAGED,
      lifecycleRules: [
        {
          id: 'archive-old-raw',
          prefix: 'raw/',
          transitions: [
            {
              storageClass: s3.StorageClass.INFREQUENT_ACCESS,
              transitionAfter: cdk.Duration.days(30),
            },
            {
              storageClass: s3.StorageClass.GLACIER,
              transitionAfter: cdk.Duration.days(90),
            },
          ],
        },
        {
          id: 'expire-tmp',
          prefix: 'tmp/',
          expiration: cdk.Duration.days(7),
        },
      ],
      cors: [
        {
          allowedMethods: [s3.HttpMethods.GET, s3.HttpMethods.PUT, s3.HttpMethods.POST],
          allowedOrigins: ['*'],
          allowedHeaders: ['*'],
          maxAge: 3600,
        },
      ],
    });

    // Pipeline configuration — defines transformation steps
    this.pipelineConfigTable = new dynamodb.Table(this, 'PipelineConfigTable', {
      tableName: 'streamforge-pipelines',
      partitionKey: { name: 'pipeline_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      pointInTimeRecovery: true,
    });

    // Pipeline run history — tracks every execution
    this.runHistoryTable = new dynamodb.Table(this, 'RunHistoryTable', {
      tableName: 'streamforge-runs',
      partitionKey: { name: 'pipeline_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'run_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      timeToLiveAttribute: 'ttl',
    });

    this.runHistoryTable.addGlobalSecondaryIndex({
      indexName: 'by-status',
      partitionKey: { name: 'status', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'started_at', type: dynamodb.AttributeType.NUMBER },
    });

    // Anomaly alerts
    this.alertsTable = new dynamodb.Table(this, 'AlertsTable', {
      tableName: 'streamforge-alerts',
      partitionKey: { name: 'pipeline_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'alert_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      timeToLiveAttribute: 'ttl',
    });

    // Glue Data Catalog — schema registry for the data lake
    this.glueDatabase = new glue.CfnDatabase(this, 'GlueDatabase', {
      catalogId: this.account,
      databaseInput: {
        name: 'streamforge',
        description: 'StreamForge data lake catalog',
      },
    });

    // Glue table for raw events
    new glue.CfnTable(this, 'RawEventsTable', {
      catalogId: this.account,
      databaseName: 'streamforge',
      tableInput: {
        name: 'raw_events',
        description: 'Raw ingested events in Parquet format',
        tableType: 'EXTERNAL_TABLE',
        parameters: {
          'classification': 'parquet',
          'parquet.compression': 'SNAPPY',
        },
        storageDescriptor: {
          location: `s3://${this.dataLakeBucket.bucketName}/raw/`,
          inputFormat: 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat',
          outputFormat: 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat',
          serdeInfo: {
            serializationLibrary: 'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe',
          },
          columns: [
            { name: 'event_id', type: 'string' },
            { name: 'pipeline_id', type: 'string' },
            { name: 'timestamp', type: 'bigint' },
            { name: 'source', type: 'string' },
            { name: 'event_type', type: 'string' },
            { name: 'payload', type: 'string' },
            { name: 'ingested_at', type: 'bigint' },
          ],
        },
        partitionKeys: [
          { name: 'year', type: 'string' },
          { name: 'month', type: 'string' },
          { name: 'day', type: 'string' },
        ],
      },
    });

    // Glue table for clean/transformed events
    new glue.CfnTable(this, 'CleanEventsTable', {
      catalogId: this.account,
      databaseName: 'streamforge',
      tableInput: {
        name: 'clean_events',
        description: 'Transformed and validated events',
        tableType: 'EXTERNAL_TABLE',
        parameters: {
          'classification': 'parquet',
          'parquet.compression': 'SNAPPY',
        },
        storageDescriptor: {
          location: `s3://${this.dataLakeBucket.bucketName}/clean/`,
          inputFormat: 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat',
          outputFormat: 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat',
          serdeInfo: {
            serializationLibrary: 'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe',
          },
          columns: [
            { name: 'event_id', type: 'string' },
            { name: 'pipeline_id', type: 'string' },
            { name: 'timestamp', type: 'bigint' },
            { name: 'source', type: 'string' },
            { name: 'event_type', type: 'string' },
            { name: 'payload', type: 'string' },
            { name: 'processed_at', type: 'bigint' },
            { name: 'is_anomaly', type: 'boolean' },
            { name: 'anomaly_score', type: 'double' },
          ],
        },
        partitionKeys: [
          { name: 'year', type: 'string' },
          { name: 'month', type: 'string' },
          { name: 'day', type: 'string' },
        ],
      },
    });

    // Outputs
    new cdk.CfnOutput(this, 'DataLakeBucketName', {
      value: this.dataLakeBucket.bucketName,
      description: 'S3 data lake bucket',
    });

    new cdk.CfnOutput(this, 'GlueDatabaseName', {
      value: 'streamforge',
      description: 'Glue catalog database',
    });
  }
}
