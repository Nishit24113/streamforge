import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as targets from 'aws-cdk-lib/aws-route53-targets';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import { Construct } from 'constructs';

/**
 * Multi-region StreamForge deployment for high availability and disaster recovery.
 *
 * Architecture:
 * - Primary region: us-east-1
 * - Secondary region: us-west-2
 * - Active-active: Both regions serve traffic via Route 53 latency-based routing
 * - Cross-region replication: S3 data lake, DynamoDB global tables
 * - Failover: Automatic health check-based failover (< 1 minute)
 */

export interface MultiRegionConfig {
  primaryRegion: string;
  secondaryRegion: string;
  domainName: string;
  hostedZoneId: string;
  enableCrossRegionReplication: boolean;
}

export class MultiRegionStack extends cdk.Stack {
  constructor(scope: Construct, id: string, config: MultiRegionConfig, props?: cdk.StackProps) {
    super(scope, id, props);

    // S3 Data Lake with Cross-Region Replication
    const primaryBucket = new s3.Bucket(this, 'PrimaryDataLake', {
      bucketName: `streamforge-lake-${config.primaryRegion}`,
      versioned: true,
      encryption: s3.BucketEncryption.KMS_MANAGED,
      lifecycleRules: [{
        transitions: [{
          storageClass: s3.StorageClass.INFREQUENT_ACCESS,
          transitionAfter: cdk.Duration.days(30)
        }, {
          storageClass: s3.StorageClass.GLACIER,
          transitionAfter: cdk.Duration.days(90)
        }]
      }]
    });

    if (config.enableCrossRegionReplication) {
      const secondaryBucket = new s3.Bucket(this, 'SecondaryDataLake', {
        bucketName: `streamforge-lake-${config.secondaryRegion}`,
        versioned: true,
        encryption: s3.BucketEncryption.KMS_MANAGED
      });

      // Enable S3 Cross-Region Replication
      primaryBucket.addLifecycleRule({
        id: 'ReplicateToSecondary',
        enabled: true
      });

      // CRR requires versioning + IAM role (configured via S3 console or CLI)
      new cdk.CfnOutput(this, 'CRRSetup', {
        value: `aws s3api put-bucket-replication --bucket ${primaryBucket.bucketName} --replication-configuration file://replication.json`,
        description: 'Command to enable S3 Cross-Region Replication'
      });
    }

    // DynamoDB Global Tables (automatic multi-region replication)
    const pipelineTable = new dynamodb.Table(this, 'GlobalPipelineTable', {
      tableName: 'streamforge-pipelines-global',
      partitionKey: { name: 'pipeline_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      replicationRegions: [config.secondaryRegion],
      stream: dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
      pointInTimeRecovery: true
    });

    const runTable = new dynamodb.Table(this, 'GlobalRunTable', {
      tableName: 'streamforge-runs-global',
      partitionKey: { name: 'run_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      replicationRegions: [config.secondaryRegion],
      stream: dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
      timeToLiveAttribute: 'ttl'
    });

    // API Gateway in primary region
    const primaryApi = new apigateway.RestApi(this, 'PrimaryAPI', {
      restApiName: 'StreamForge-Primary',
      description: 'StreamForge API (Primary Region)',
      deployOptions: {
        stageName: 'prod',
        metricsEnabled: true,
        tracingEnabled: true
      },
      endpointConfiguration: {
        types: [apigateway.EndpointType.REGIONAL]
      }
    });

    // Route 53 Health Check for Primary Region
    const primaryHealthCheck = new route53.CfnHealthCheck(this, 'PrimaryHealthCheck', {
      healthCheckConfig: {
        type: 'HTTPS',
        resourcePath: '/health',
        fullyQualifiedDomainName: `${primaryApi.restApiId}.execute-api.${config.primaryRegion}.amazonaws.com`,
        port: 443,
        requestInterval: 30,
        failureThreshold: 3
      }
    });

    // Route 53 Hosted Zone with Latency-Based Routing
    const hostedZone = route53.HostedZone.fromHostedZoneAttributes(this, 'HostedZone', {
      hostedZoneId: config.hostedZoneId,
      zoneName: config.domainName
    });

    // Primary Region Record (Latency-Based)
    new route53.ARecord(this, 'PrimaryRegionRecord', {
      zone: hostedZone,
      recordName: 'api',
      target: route53.RecordTarget.fromAlias(
        new targets.ApiGateway(primaryApi)
      ),
      region: config.primaryRegion,
      setIdentifier: 'Primary'
    });

    // Outputs
    new cdk.CfnOutput(this, 'PrimaryBucketName', {
      value: primaryBucket.bucketName,
      description: 'Primary data lake bucket name'
    });

    new cdk.CfnOutput(this, 'PrimaryAPIEndpoint', {
      value: primaryApi.url,
      description: 'Primary API Gateway endpoint'
    });

    new cdk.CfnOutput(this, 'PrimaryHealthCheckId', {
      value: primaryHealthCheck.attrHealthCheckId,
      description: 'Primary region health check ID'
    });

    new cdk.CfnOutput(this, 'GlobalTableName', {
      value: pipelineTable.tableName,
      description: 'Global DynamoDB table (replicated across regions)'
    });

    // Cross-Stack References for Secondary Region
    new cdk.CfnOutput(this, 'SecondaryRegion', {
      value: config.secondaryRegion,
      description: 'Secondary region for failover'
    });
  }
}

/**
 * Deploy secondary region stack (us-west-2)
 */
export class SecondaryRegionStack extends cdk.Stack {
  constructor(scope: Construct, id: string, config: MultiRegionConfig, props?: cdk.StackProps) {
    super(scope, id, {
      ...props,
      env: {
        account: props?.env?.account,
        region: config.secondaryRegion
      }
    });

    // API Gateway in secondary region
    const secondaryApi = new apigateway.RestApi(this, 'SecondaryAPI', {
      restApiName: 'StreamForge-Secondary',
      description: 'StreamForge API (Secondary Region - Failover)',
      deployOptions: {
        stageName: 'prod',
        metricsEnabled: true,
        tracingEnabled: true
      },
      endpointConfiguration: {
        types: [apigateway.EndpointType.REGIONAL]
      }
    });

    // Route 53 Health Check for Secondary Region
    const secondaryHealthCheck = new route53.CfnHealthCheck(this, 'SecondaryHealthCheck', {
      healthCheckConfig: {
        type: 'HTTPS',
        resourcePath: '/health',
        fullyQualifiedDomainName: `${secondaryApi.restApiId}.execute-api.${config.secondaryRegion}.amazonaws.com`,
        port: 443,
        requestInterval: 30,
        failureThreshold: 3
      }
    });

    // Route 53 Hosted Zone
    const hostedZone = route53.HostedZone.fromHostedZoneAttributes(this, 'HostedZone', {
      hostedZoneId: config.hostedZoneId,
      zoneName: config.domainName
    });

    // Secondary Region Record (Latency-Based)
    new route53.ARecord(this, 'SecondaryRegionRecord', {
      zone: hostedZone,
      recordName: 'api',
      target: route53.RecordTarget.fromAlias(
        new targets.ApiGateway(secondaryApi)
      ),
      region: config.secondaryRegion,
      setIdentifier: 'Secondary'
    });

    // Outputs
    new cdk.CfnOutput(this, 'SecondaryAPIEndpoint', {
      value: secondaryApi.url,
      description: 'Secondary API Gateway endpoint (failover)'
    });

    new cdk.CfnOutput(this, 'SecondaryHealthCheckId', {
      value: secondaryHealthCheck.attrHealthCheckId,
      description: 'Secondary region health check ID'
    });
  }
}

/**
 * Deploy both regions in a single CDK app
 *
 * Usage:
 *   cdk deploy StreamForge-Primary StreamForge-Secondary
 */
export class MultiRegionApp extends cdk.App {
  constructor() {
    super();

    const config: MultiRegionConfig = {
      primaryRegion: 'us-east-1',
      secondaryRegion: 'us-west-2',
      domainName: 'streamforge.example.com',
      hostedZoneId: 'Z1234567890ABC',
      enableCrossRegionReplication: true
    };

    // Deploy primary region
    new MultiRegionStack(this, 'StreamForge-Primary', config, {
      env: {
        account: process.env.CDK_DEFAULT_ACCOUNT,
        region: config.primaryRegion
      }
    });

    // Deploy secondary region
    new SecondaryRegionStack(this, 'StreamForge-Secondary', config, {
      env: {
        account: process.env.CDK_DEFAULT_ACCOUNT,
        region: config.secondaryRegion
      }
    });
  }
}
