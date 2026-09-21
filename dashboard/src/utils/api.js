import axios from 'axios';

const INGESTION_API = import.meta.env.VITE_INGESTION_API || '';
const ANALYTICS_API = import.meta.env.VITE_ANALYTICS_API || '';

const ingestionClient = axios.create({
  baseURL: INGESTION_API,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

const analyticsClient = axios.create({
  baseURL: ANALYTICS_API,
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
});

export const checkHealth = async () => {
  if (!INGESTION_API) return { status: 'local', service: 'streamforge-demo' };
  const { data } = await ingestionClient.get('/health');
  return data;
};

export const ingestEvents = async (pipeline, events) => {
  if (!INGESTION_API) return mockIngest(pipeline, events);
  const { data } = await ingestionClient.post('/ingest', { pipeline, events });
  return data;
};

export const listPipelines = async () => {
  if (!INGESTION_API) return mockPipelines();
  const { data } = await ingestionClient.get('/pipelines');
  return data;
};

export const createPipeline = async (config) => {
  if (!INGESTION_API) return { status: 'created', pipeline: config };
  const { data } = await ingestionClient.post('/pipelines', config);
  return data;
};

export const getPipelineRuns = async (pipelineId) => {
  if (!INGESTION_API) return mockRuns(pipelineId);
  const { data } = await ingestionClient.get(`/pipelines/${pipelineId}/runs`);
  return data;
};

export const getStats = async () => {
  if (!ANALYTICS_API) return mockStats();
  const { data } = await analyticsClient.get('/stats');
  return data;
};

export const runQuery = async (sql) => {
  if (!ANALYTICS_API) return mockQuery(sql);
  const { data } = await analyticsClient.post('/query', { sql });
  return data;
};

export const getQueryResults = async (queryId) => {
  if (!ANALYTICS_API) return mockQueryResults(queryId);
  const { data } = await analyticsClient.get(`/query/${queryId}`);
  return data;
};

export const getAnomalies = async (pipelineId) => {
  if (!ANALYTICS_API) return mockAnomalies(pipelineId);
  const params = pipelineId ? `?pipeline_id=${pipelineId}` : '';
  const { data } = await analyticsClient.get(`/anomalies${params}`);
  return data;
};

// Mock data for local development
function mockIngest(pipeline, events) {
  return {
    status: 'accepted',
    pipeline,
    run_id: `run-${Date.now().toString(36)}`,
    events_received: events.length,
    events_failed: 0,
  };
}

function mockPipelines() {
  return {
    pipelines: [
      { pipeline_id: 'ecommerce-events', name: 'E-Commerce Events', status: 'ACTIVE', created_at: Date.now() / 1000 - 86400 * 7 },
      { pipeline_id: 'iot-sensors', name: 'IoT Sensor Data', status: 'ACTIVE', created_at: Date.now() / 1000 - 86400 * 5 },
      { pipeline_id: 'web-analytics', name: 'Web Analytics', status: 'ACTIVE', created_at: Date.now() / 1000 - 86400 * 3 },
    ],
    count: 3,
  };
}

function mockRuns(pipelineId) {
  const statuses = ['COMPLETED', 'COMPLETED', 'COMPLETED', 'PROCESSING', 'FAILED'];
  const runs = Array.from({ length: 15 }, (_, i) => ({
    pipeline_id: pipelineId,
    run_id: `run-${(Date.now() - i * 3600000).toString(36)}`,
    status: statuses[i % statuses.length],
    started_at: (Date.now() / 1000) - (i * 3600),
    completed_at: (Date.now() / 1000) - (i * 3600) + 12,
    events_count: Math.floor(Math.random() * 500) + 50,
    anomaly_count: Math.floor(Math.random() * 10),
  }));
  return { pipeline_id: pipelineId, runs, count: runs.length };
}

function mockStats() {
  return {
    total_events: 247893,
    total_anomalies: 1247,
    total_runs: 892,
    completed_runs: 856,
    failed_runs: 12,
    active_pipelines: 3,
    anomaly_rate: 0.5,
    pipeline_stats: {
      'ecommerce-events': { runs: 312, events: 98450, anomalies: 523 },
      'iot-sensors': { runs: 380, events: 112340, anomalies: 487 },
      'web-analytics': { runs: 200, events: 37103, anomalies: 237 },
    },
  };
}

function mockQuery(sql) {
  return {
    status: 'completed',
    query_id: `q-${Date.now().toString(36)}`,
    columns: ['event_type', 'event_count', 'event_date'],
    rows: [
      { event_type: 'purchase', event_count: '1247', event_date: '2026-09-18' },
      { event_type: 'page_view', event_count: '8923', event_date: '2026-09-18' },
      { event_type: 'signup', event_count: '234', event_date: '2026-09-18' },
      { event_type: 'add_to_cart', event_count: '3412', event_date: '2026-09-18' },
    ],
    row_count: 4,
    bytes_scanned: 1048576,
    execution_time_ms: 2340,
  };
}

function mockQueryResults(queryId) {
  return {
    status: 'completed',
    query_id: queryId,
    columns: ['event_type', 'event_count', 'event_date'],
    rows: [
      { event_type: 'purchase', event_count: '1247', event_date: '2026-09-18' },
      { event_type: 'page_view', event_count: '8923', event_date: '2026-09-18' },
      { event_type: 'signup', event_count: '234', event_date: '2026-09-18' },
      { event_type: 'add_to_cart', event_count: '3412', event_date: '2026-09-18' },
    ],
    row_count: 4,
    bytes_scanned: 1048576,
    execution_time_ms: 2340,
  };
}

function mockAnomalies(pipelineId) {
  const now = Date.now();
  const anomalies = Array.from({ length: 20 }, (_, i) => ({
    pipeline_id: pipelineId || ['ecommerce-events', 'iot-sensors', 'web-analytics'][i % 3],
    alert_id: `alert-${(now - i * 1800000).toString(36)}`,
    event_type: ['purchase', 'temperature', 'page_view'][i % 3],
    anomaly_score: (0.6 + Math.random() * 0.4).toFixed(4),
    severity: Math.random() > 0.5 ? 'HIGH' : 'MEDIUM',
    timestamp: now - i * 1800000,
    created_at: (now / 1000) - (i * 1800),
  }));
  return { anomalies, count: anomalies.length };
}
