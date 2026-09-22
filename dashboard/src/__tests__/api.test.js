import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// We need to test the api module with different env states, so we dynamically import it
// and use vi.stubEnv / vi.unstubEnv (vitest 2.x) or mock import.meta.env

describe('API client - mock mode (no API URL)', () => {
  let api;

  beforeEach(async () => {
    // Reset modules so import.meta.env is re-evaluated
    vi.resetModules();
    // Import with default empty env (mock mode)
    api = await import('../utils/api');
  });

  it('checkHealth returns local status when no API URL', async () => {
    const result = await api.checkHealth();
    expect(result).toHaveProperty('status');
    expect(result.status).toBe('local');
    expect(result.service).toBe('streamforge-demo');
  });

  it('getStats returns mock stats with correct shape', async () => {
    const result = await api.getStats();
    expect(result).toHaveProperty('total_events');
    expect(result).toHaveProperty('total_anomalies');
    expect(result).toHaveProperty('total_runs');
    expect(result).toHaveProperty('completed_runs');
    expect(result).toHaveProperty('failed_runs');
    expect(result).toHaveProperty('active_pipelines');
    expect(result).toHaveProperty('anomaly_rate');
    expect(result).toHaveProperty('pipeline_stats');
    expect(typeof result.total_events).toBe('number');
  });

  it('listPipelines returns array of pipeline objects', async () => {
    const result = await api.listPipelines();
    expect(result).toHaveProperty('pipelines');
    expect(Array.isArray(result.pipelines)).toBe(true);
    expect(result.pipelines.length).toBe(3);
    result.pipelines.forEach((p) => {
      expect(p).toHaveProperty('pipeline_id');
      expect(p).toHaveProperty('name');
      expect(p).toHaveProperty('status');
      expect(p).toHaveProperty('created_at');
    });
  });

  it('ingestEvents returns accepted result with correct fields', async () => {
    const events = [{ event_type: 'test', timestamp: Date.now() }];
    const result = await api.ingestEvents('test-pipeline', events);
    expect(result).toHaveProperty('status', 'accepted');
    expect(result).toHaveProperty('pipeline', 'test-pipeline');
    expect(result).toHaveProperty('run_id');
    expect(result).toHaveProperty('events_received', 1);
    expect(result).toHaveProperty('events_failed', 0);
  });

  it('getPipelineRuns returns runs array for given pipeline', async () => {
    const result = await api.getPipelineRuns('ecommerce-events');
    expect(result).toHaveProperty('pipeline_id', 'ecommerce-events');
    expect(result).toHaveProperty('runs');
    expect(Array.isArray(result.runs)).toBe(true);
    expect(result.runs.length).toBeGreaterThan(0);
    result.runs.forEach((r) => {
      expect(r).toHaveProperty('run_id');
      expect(r).toHaveProperty('status');
      expect(r).toHaveProperty('events_count');
    });
  });

  it('runQuery returns completed result with columns and rows', async () => {
    const result = await api.runQuery('SELECT * FROM test');
    expect(result).toHaveProperty('status', 'completed');
    expect(result).toHaveProperty('columns');
    expect(result).toHaveProperty('rows');
    expect(result).toHaveProperty('row_count');
    expect(result).toHaveProperty('bytes_scanned');
    expect(result).toHaveProperty('execution_time_ms');
    expect(Array.isArray(result.columns)).toBe(true);
    expect(Array.isArray(result.rows)).toBe(true);
    expect(result.row_count).toBe(4);
  });

  it('getQueryResults returns completed result with query_id', async () => {
    const result = await api.getQueryResults('q-test123');
    expect(result).toHaveProperty('status', 'completed');
    expect(result).toHaveProperty('query_id', 'q-test123');
    expect(result).toHaveProperty('columns');
    expect(result).toHaveProperty('rows');
  });

  it('getAnomalies returns anomalies array', async () => {
    const result = await api.getAnomalies();
    expect(result).toHaveProperty('anomalies');
    expect(result).toHaveProperty('count');
    expect(Array.isArray(result.anomalies)).toBe(true);
    expect(result.anomalies.length).toBe(20);
    result.anomalies.forEach((a) => {
      expect(a).toHaveProperty('pipeline_id');
      expect(a).toHaveProperty('alert_id');
      expect(a).toHaveProperty('anomaly_score');
      expect(a).toHaveProperty('severity');
      expect(['HIGH', 'MEDIUM']).toContain(a.severity);
    });
  });

  it('getAnomalies with pipeline filter still returns correct shape', async () => {
    const result = await api.getAnomalies('ecommerce-events');
    expect(result).toHaveProperty('anomalies');
    expect(Array.isArray(result.anomalies)).toBe(true);
  });

  it('mock stats pipeline_stats has data for all 3 pipelines', async () => {
    const result = await api.getStats();
    const pipelineKeys = Object.keys(result.pipeline_stats);
    expect(pipelineKeys).toContain('ecommerce-events');
    expect(pipelineKeys).toContain('iot-sensors');
    expect(pipelineKeys).toContain('web-analytics');
  });

  it('mock runs have valid statuses', async () => {
    const result = await api.getPipelineRuns('test');
    const validStatuses = ['COMPLETED', 'PROCESSING', 'FAILED'];
    result.runs.forEach((r) => {
      expect(validStatuses).toContain(r.status);
    });
  });

  it('mock query rows have matching column values', async () => {
    const result = await api.runQuery('SELECT * FROM events');
    const { columns, rows } = result;
    rows.forEach((row) => {
      columns.forEach((col) => {
        expect(row).toHaveProperty(col);
      });
    });
  });
});
