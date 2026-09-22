/**
 * Comprehensive tests for the StreamForge Node.js/TypeScript SDK.
 *
 * Mocks the global fetch to isolate all network calls.
 * Run with: npx vitest run src/__tests__/index.test.ts
 *           (or Jest with ts-jest / vitest)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { StreamForge, StreamForgeError } from '../index.js';
import type { StreamForgeConfig } from '../index.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockFetchResponse(body: unknown, status = 200, ok = true) {
  return vi.fn().mockResolvedValueOnce({
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  });
}

function mockFetchSequence(responses: Array<{ body: unknown; status: number; ok: boolean }>) {
  const fn = vi.fn();
  for (const r of responses) {
    fn.mockResolvedValueOnce({
      ok: r.ok,
      status: r.status,
      statusText: r.ok ? 'OK' : 'Error',
      json: () => Promise.resolve(r.body),
      text: () => Promise.resolve(JSON.stringify(r.body)),
    });
  }
  return fn;
}

const BASE_CONFIG: StreamForgeConfig = {
  apiUrl: 'https://api.example.com/v1/',
  apiKey: 'test-key',
  orgId: 'test-org',
  maxRetries: 1,
  retryBaseDelay: 0,
};

// ---------------------------------------------------------------------------
// Client Construction
// ---------------------------------------------------------------------------

describe('StreamForge Client Construction', () => {
  it('normalizes trailing slashes from apiUrl', () => {
    const client = new StreamForge({ apiUrl: 'https://api.example.com/v1/' });
    // Access private field via any cast for test verification
    expect((client as any).apiUrl).toBe('https://api.example.com/v1');
  });

  it('defaults analyticsUrl to apiUrl', () => {
    const client = new StreamForge({ apiUrl: 'https://api.example.com' });
    expect((client as any).analyticsUrl).toBe('https://api.example.com');
  });

  it('allows separate analyticsUrl', () => {
    const client = new StreamForge({
      apiUrl: 'https://api.example.com',
      analyticsUrl: 'https://analytics.example.com/',
    });
    expect((client as any).analyticsUrl).toBe('https://analytics.example.com');
  });

  it('defaults maxRetries to 3', () => {
    const client = new StreamForge({ apiUrl: 'https://api.example.com' });
    expect((client as any).maxRetries).toBe(3);
  });

  it('defaults retryBaseDelay to 500', () => {
    const client = new StreamForge({ apiUrl: 'https://api.example.com' });
    expect((client as any).retryBaseDelay).toBe(500);
  });
});

// ---------------------------------------------------------------------------
// Headers / org_id
// ---------------------------------------------------------------------------

describe('Headers', () => {
  let client: StreamForge;

  beforeEach(() => {
    client = new StreamForge(BASE_CONFIG);
  });

  it('sends X-Org-Id header on requests', async () => {
    const mockFetch = mockFetchResponse({ status: 'ok' });
    vi.stubGlobal('fetch', mockFetch);

    await client.health();

    const headers = mockFetch.mock.calls[0][1].headers;
    expect(headers['X-Org-Id']).toBe('test-org');
  });

  it('sends Authorization Bearer header when apiKey is set', async () => {
    const mockFetch = mockFetchResponse({ status: 'ok' });
    vi.stubGlobal('fetch', mockFetch);

    await client.health();

    const headers = mockFetch.mock.calls[0][1].headers;
    expect(headers['Authorization']).toBe('Bearer test-key');
  });

  it('omits Authorization header when no apiKey', async () => {
    const noKeyClient = new StreamForge({ apiUrl: 'https://api.example.com', maxRetries: 1, retryBaseDelay: 0 });
    const mockFetch = mockFetchResponse({ status: 'ok' });
    vi.stubGlobal('fetch', mockFetch);

    await noKeyClient.health();

    const headers = mockFetch.mock.calls[0][1].headers;
    expect(headers['Authorization']).toBeUndefined();
  });

  it('sends Content-Type application/json', async () => {
    const mockFetch = mockFetchResponse({ status: 'ok' });
    vi.stubGlobal('fetch', mockFetch);

    await client.health();

    const headers = mockFetch.mock.calls[0][1].headers;
    expect(headers['Content-Type']).toBe('application/json');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });
});

// ---------------------------------------------------------------------------
// ingest()
// ---------------------------------------------------------------------------

describe('ingest()', () => {
  let client: StreamForge;

  beforeEach(() => {
    client = new StreamForge(BASE_CONFIG);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends POST with pipeline and events', async () => {
    const mockFetch = mockFetchResponse({ accepted: 2 });
    vi.stubGlobal('fetch', mockFetch);

    const events = [{ user: 'a' }, { user: 'b' }];
    const result = await client.ingest('my-pipeline', events);

    expect(result.accepted).toBe(2);
    expect(mockFetch).toHaveBeenCalledTimes(1);

    const [url, opts] = mockFetch.mock.calls[0];
    expect(url).toBe('https://api.example.com/v1/ingest');
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body)).toEqual({ pipeline: 'my-pipeline', events });
  });
});

// ---------------------------------------------------------------------------
// ingestBatch()
// ---------------------------------------------------------------------------

describe('ingestBatch()', () => {
  let client: StreamForge;

  beforeEach(() => {
    client = new StreamForge(BASE_CONFIG);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('chunks events and aggregates accepted count', async () => {
    const mockFetch = mockFetchSequence([
      { body: { accepted: 2 }, status: 200, ok: true },
      { body: { accepted: 2 }, status: 200, ok: true },
      { body: { accepted: 1 }, status: 200, ok: true },
    ]);
    vi.stubGlobal('fetch', mockFetch);

    const events = Array.from({ length: 5 }, (_, i) => ({ i }));
    const result = await client.ingestBatch('pipe', events, 2);

    expect(result.accepted).toBe(5);
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it('sends all events in one batch when under batchSize', async () => {
    const mockFetch = mockFetchResponse({ accepted: 3 });
    vi.stubGlobal('fetch', mockFetch);

    const events = [{ a: 1 }, { a: 2 }, { a: 3 }];
    const result = await client.ingestBatch('pipe', events, 500);

    expect(result.accepted).toBe(3);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// query() — auto-poll
// ---------------------------------------------------------------------------

describe('query()', () => {
  let client: StreamForge;

  beforeEach(() => {
    client = new StreamForge({
      ...BASE_CONFIG,
      analyticsUrl: 'https://analytics.example.com',
    });
    // Speed up the sleep to avoid slow tests
    vi.spyOn(client as any, 'sleep').mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('returns immediately when status is completed', async () => {
    const mockFetch = mockFetchResponse({
      id: 'q-1',
      status: 'completed',
      rows: [{ x: 1 }],
    });
    vi.stubGlobal('fetch', mockFetch);

    const result = await client.query('SELECT 1');
    expect(result.status).toBe('completed');
    expect(result.rows).toEqual([{ x: 1 }]);
    // Only one call (no polling)
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('polls until completion', async () => {
    const mockFetch = mockFetchSequence([
      { body: { id: 'q-1', status: 'running' }, status: 200, ok: true },
      { body: { id: 'q-1', status: 'running' }, status: 200, ok: true },
      { body: { id: 'q-1', status: 'completed', rows: [{ x: 42 }] }, status: 200, ok: true },
    ]);
    vi.stubGlobal('fetch', mockFetch);

    const result = await client.query('SELECT * FROM t');
    expect(result.status).toBe('completed');
    expect(result.rows).toEqual([{ x: 42 }]);
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it('throws on query failure', async () => {
    const mockFetch = mockFetchSequence([
      { body: { id: 'q-1', status: 'running' }, status: 200, ok: true },
      { body: { id: 'q-1', status: 'failed' }, status: 200, ok: true },
    ]);
    vi.stubGlobal('fetch', mockFetch);

    await expect(client.query('SELECT bad')).rejects.toThrow(StreamForgeError);
  });
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

describe('Error handling', () => {
  let client: StreamForge;

  beforeEach(() => {
    client = new StreamForge({ ...BASE_CONFIG, maxRetries: 1, retryBaseDelay: 0 });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('throws StreamForgeError on 404', async () => {
    const mockFetch = mockFetchResponse({ error: 'not found' }, 404, false);
    vi.stubGlobal('fetch', mockFetch);

    await expect(client.health()).rejects.toThrow(StreamForgeError);
    try {
      await client.health();
    } catch (err) {
      expect(err).toBeInstanceOf(StreamForgeError);
      expect((err as StreamForgeError).statusCode).toBe(404);
    }
  });

  it('throws StreamForgeError on 500', async () => {
    const mockFetch = mockFetchResponse({ error: 'server error' }, 500, false);
    vi.stubGlobal('fetch', mockFetch);

    await expect(client.health()).rejects.toThrow(StreamForgeError);
  });

  it('does not retry 4xx errors (except 429)', async () => {
    const mockFetch = mockFetchResponse({ error: 'bad request' }, 400, false);
    vi.stubGlobal('fetch', mockFetch);

    const multiRetryClient = new StreamForge({ ...BASE_CONFIG, maxRetries: 3, retryBaseDelay: 0 });

    await expect(multiRetryClient.health()).rejects.toThrow(StreamForgeError);
    // Should not retry 400 — only 1 call
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// Retry logic
// ---------------------------------------------------------------------------

describe('Retry logic', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('retries 429 with exponential backoff', async () => {
    const client = new StreamForge({ ...BASE_CONFIG, maxRetries: 3, retryBaseDelay: 10 });
    const sleepSpy = vi.spyOn(client as any, 'sleep').mockResolvedValue(undefined);

    const mockFetch = mockFetchSequence([
      { body: { error: 'rate limited' }, status: 429, ok: false },
      { body: { error: 'rate limited' }, status: 429, ok: false },
      { body: { status: 'ok' }, status: 200, ok: true },
    ]);
    vi.stubGlobal('fetch', mockFetch);

    const result = await client.health();
    expect(result).toEqual({ status: 'ok' });
    expect(mockFetch).toHaveBeenCalledTimes(3);
    // Backoff delays: 10 * 2^0 = 10, 10 * 2^1 = 20
    expect(sleepSpy).toHaveBeenCalledWith(10);
    expect(sleepSpy).toHaveBeenCalledWith(20);
  });

  it('retries 500 server errors', async () => {
    const client = new StreamForge({ ...BASE_CONFIG, maxRetries: 2, retryBaseDelay: 0 });
    vi.spyOn(client as any, 'sleep').mockResolvedValue(undefined);

    const mockFetch = mockFetchSequence([
      { body: { error: 'server error' }, status: 500, ok: false },
      { body: { status: 'ok' }, status: 200, ok: true },
    ]);
    vi.stubGlobal('fetch', mockFetch);

    const result = await client.health();
    expect(result).toEqual({ status: 'ok' });
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('throws after exhausting retries', async () => {
    const client = new StreamForge({ ...BASE_CONFIG, maxRetries: 2, retryBaseDelay: 0 });
    vi.spyOn(client as any, 'sleep').mockResolvedValue(undefined);

    const mockFetch = mockFetchSequence([
      { body: { error: 'server error' }, status: 500, ok: false },
      { body: { error: 'server error' }, status: 500, ok: false },
    ]);
    vi.stubGlobal('fetch', mockFetch);

    await expect(client.health()).rejects.toThrow(StreamForgeError);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});

// ---------------------------------------------------------------------------
// Pipeline CRUD
// ---------------------------------------------------------------------------

describe('Pipeline operations', () => {
  let client: StreamForge;

  beforeEach(() => {
    client = new StreamForge(BASE_CONFIG);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('createPipeline sends POST /pipelines', async () => {
    const mockFetch = mockFetchResponse({ id: 'p-1', name: 'test' });
    vi.stubGlobal('fetch', mockFetch);

    const result = await client.createPipeline({ name: 'test' });
    expect(result.id).toBe('p-1');

    const [url, opts] = mockFetch.mock.calls[0];
    expect(url).toBe('https://api.example.com/v1/pipelines');
    expect(opts.method).toBe('POST');
  });

  it('listPipelines sends GET /pipelines', async () => {
    const mockFetch = mockFetchResponse([{ id: 'p-1' }, { id: 'p-2' }]);
    vi.stubGlobal('fetch', mockFetch);

    const result = await client.listPipelines();
    expect(result).toHaveLength(2);

    const [url, opts] = mockFetch.mock.calls[0];
    expect(url).toBe('https://api.example.com/v1/pipelines');
    expect(opts.method).toBe('GET');
  });

  it('getPipeline sends GET /pipelines/:id', async () => {
    const mockFetch = mockFetchResponse({ id: 'p-1', name: 'clicks' });
    vi.stubGlobal('fetch', mockFetch);

    const result = await client.getPipeline('p-1');
    expect(result.name).toBe('clicks');

    const [url] = mockFetch.mock.calls[0];
    expect(url).toBe('https://api.example.com/v1/pipelines/p-1');
  });

  it('getRuns sends GET /pipelines/:id/runs', async () => {
    const mockFetch = mockFetchResponse([{ id: 'r-1', pipelineId: 'p-1', status: 'completed' }]);
    vi.stubGlobal('fetch', mockFetch);

    const result = await client.getRuns('p-1');
    expect(result[0].status).toBe('completed');

    const [url] = mockFetch.mock.calls[0];
    expect(url).toBe('https://api.example.com/v1/pipelines/p-1/runs');
  });
});

// ---------------------------------------------------------------------------
// Analytics endpoints
// ---------------------------------------------------------------------------

describe('Analytics', () => {
  let client: StreamForge;

  beforeEach(() => {
    client = new StreamForge({
      ...BASE_CONFIG,
      analyticsUrl: 'https://analytics.example.com',
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('getStats sends GET to analytics/stats', async () => {
    const mockFetch = mockFetchResponse({ eventsToday: 5000 });
    vi.stubGlobal('fetch', mockFetch);

    const result = await client.getStats();
    expect(result.eventsToday).toBe(5000);

    const [url] = mockFetch.mock.calls[0];
    expect(url).toBe('https://analytics.example.com/stats');
  });

  it('getAnomalies sends GET without filter', async () => {
    const mockFetch = mockFetchResponse([{ severity: 'high' }]);
    vi.stubGlobal('fetch', mockFetch);

    const result = await client.getAnomalies();
    expect(result).toHaveLength(1);

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('/anomalies');
    expect(url).not.toContain('pipelineId');
  });

  it('getAnomalies sends GET with pipelineId filter', async () => {
    const mockFetch = mockFetchResponse([]);
    vi.stubGlobal('fetch', mockFetch);

    await client.getAnomalies('p-1');

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('pipelineId=p-1');
  });
});

// ---------------------------------------------------------------------------
// health()
// ---------------------------------------------------------------------------

describe('health()', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends GET to /health', async () => {
    const client = new StreamForge(BASE_CONFIG);
    const mockFetch = mockFetchResponse({ status: 'ok' });
    vi.stubGlobal('fetch', mockFetch);

    const result = await client.health();
    expect(result.status).toBe('ok');

    const [url, opts] = mockFetch.mock.calls[0];
    expect(url).toBe('https://api.example.com/v1/health');
    expect(opts.method).toBe('GET');
  });
});
