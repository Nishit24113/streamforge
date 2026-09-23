#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { StorageStack } from '../lib/storage-stack';
import { IngestionStack } from '../lib/ingestion-stack';
import { ProcessingStack } from '../lib/processing-stack';
import { AnalyticsStack } from '../lib/analytics-stack';
import { MonitoringStack } from '../lib/monitoring-stack';

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION || 'us-west-2',
};

const storage = new StorageStack(app, 'StreamForgeStorageStack', { env });

const ingestion = new IngestionStack(app, 'StreamForgeIngestionStack', {
  env,
  dataLakeBucket: storage.dataLakeBucket,
  pipelineConfigTable: storage.pipelineConfigTable,
  runHistoryTable: storage.runHistoryTable,
});

const processing = new ProcessingStack(app, 'StreamForgeProcessingStack', {
  env,
  dataLakeBucket: storage.dataLakeBucket,
  pipelineConfigTable: storage.pipelineConfigTable,
  runHistoryTable: storage.runHistoryTable,
  alertsTable: storage.alertsTable,
  ingestionStream: ingestion.ingestionStream,
});

new AnalyticsStack(app, 'StreamForgeAnalyticsStack', {
  env,
  dataLakeBucket: storage.dataLakeBucket,
  pipelineConfigTable: storage.pipelineConfigTable,
  runHistoryTable: storage.runHistoryTable,
});

new MonitoringStack(app, 'StreamForgeMonitoringStack', {
  env,
  ingestionStream: ingestion.ingestionStream,
  pipelineStateMachine: processing.pipelineStateMachine,
  runHistoryTable: storage.runHistoryTable,
  alertsTable: storage.alertsTable,
});

app.synth();
