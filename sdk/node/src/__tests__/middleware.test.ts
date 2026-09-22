/**
 * Tests for the StreamForge Express middleware.
 *
 * Mocks the StreamForge client to isolate middleware behavior.
 * Run with: npx vitest run src/__tests__/middleware.test.ts
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { streamforgeMiddleware } from '../middleware.js';
import type { MiddlewareOptions, RequestEvent } from '../middleware.js';
import { StreamForge } from '../index.js';
import { EventEmitter } from 'events';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockClient() {
  return {
    ingest: vi.fn().mockResolvedValue({ accepted: 1 }),
  } as unknown as StreamForge;
}

function createMockReq(overrides: Record<string, unknown> = {}) {
  return {
    method: 'GET',
    originalUrl: '/api/data',
    url: '/api/data',
    headers: { 'user-agent': 'test-agent/1.0' },
    ip: '127.0.0.1',
    socket: { remoteAddress: '127.0.0.1' },
    ...overrides,
  };
}

function createMockRes(): EventEmitter & { statusCode: number } {
  const res = new EventEmitter() as EventEmitter & { statusCode: number };
  res.statusCode = 200;
  return res;
}

// ---------------------------------------------------------------------------
// Core behavior
// ---------------------------------------------------------------------------

describe('streamforgeMiddleware', () => {
  let mockClient: ReturnType<typeof createMockClient>;

  beforeEach(() => {
    mockClient = createMockClient();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('captures request method, path, status, and duration', async () => {
    const middleware = streamforgeMiddleware({
      pipelineId: 'web-analytics',
      client: mockClient,
      flushInterval: 100,
      maxBufferSize: 1,
    });

    const req = createMockReq({ method: 'POST', originalUrl: '/api/users' });
    const res = createMockRes();
    res.statusCode = 201;
    const next = vi.fn();

    middleware(req, res, next);
    expect(next).toHaveBeenCalledTimes(1);

    // Simulate response finishing
    res.emit('finish');

    // maxBufferSize is 1, so flush should be triggered
    // Allow the flush promise to resolve
    await vi.advanceTimersByTimeAsync(0);

    expect(mockClient.ingest).toHaveBeenCalledTimes(1);
    const [pipelineId, events] = (mockClient.ingest as any).mock.calls[0];
    expect(pipelineId).toBe('web-analytics');
    expect(events).toHaveLength(1);

    const event = events[0] as RequestEvent;
    expect(event.method).toBe('POST');
    expect(event.path).toBe('/api/users');
    expect(event.statusCode).toBe(201);
    expect(typeof event.durationMs).toBe('number');
    expect(event.durationMs).toBeGreaterThanOrEqual(0);
    expect(event.timestamp).toBeDefined();
  });

  it('captures userAgent and ip', async () => {
    const middleware = streamforgeMiddleware({
      pipelineId: 'web',
      client: mockClient,
      maxBufferSize: 1,
    });

    const req = createMockReq();
    const res = createMockRes();
    const next = vi.fn();

    middleware(req, res, next);
    res.emit('finish');

    await vi.advanceTimersByTimeAsync(0);

    const events = (mockClient.ingest as any).mock.calls[0][1];
    expect(events[0].userAgent).toBe('test-agent/1.0');
    expect(events[0].ip).toBe('127.0.0.1');
  });
});

// ---------------------------------------------------------------------------
// Buffering and flushing
// ---------------------------------------------------------------------------

describe('Buffering', () => {
  let mockClient: ReturnType<typeof createMockClient>;

  beforeEach(() => {
    mockClient = createMockClient();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('buffers events and flushes on interval', async () => {
    const middleware = streamforgeMiddleware({
      pipelineId: 'web',
      client: mockClient,
      flushInterval: 5000,
      maxBufferSize: 100,
    });

    // Send a request
    const req = createMockReq();
    const res = createMockRes();
    const next = vi.fn();

    middleware(req, res, next);
    res.emit('finish');

    // Not flushed yet (buffer size < maxBufferSize)
    expect(mockClient.ingest).not.toHaveBeenCalled();

    // Advance past flush interval
    await vi.advanceTimersByTimeAsync(5000);

    expect(mockClient.ingest).toHaveBeenCalledTimes(1);
    const events = (mockClient.ingest as any).mock.calls[0][1];
    expect(events).toHaveLength(1);
  });

  it('flushes when buffer reaches maxBufferSize', async () => {
    const middleware = streamforgeMiddleware({
      pipelineId: 'web',
      client: mockClient,
      flushInterval: 60000,
      maxBufferSize: 3,
    });

    const next = vi.fn();

    // Send 3 requests to fill the buffer
    for (let i = 0; i < 3; i++) {
      const req = createMockReq({ originalUrl: `/path/${i}` });
      const res = createMockRes();
      middleware(req, res, next);
      res.emit('finish');
    }

    // Allow flush promise to resolve
    await vi.advanceTimersByTimeAsync(0);

    expect(mockClient.ingest).toHaveBeenCalledTimes(1);
    const events = (mockClient.ingest as any).mock.calls[0][1];
    expect(events).toHaveLength(3);
  });
});

// ---------------------------------------------------------------------------
// Exclusion
// ---------------------------------------------------------------------------

describe('Path exclusion', () => {
  let mockClient: ReturnType<typeof createMockClient>;

  beforeEach(() => {
    mockClient = createMockClient();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('excludes paths matching exact strings', async () => {
    const middleware = streamforgeMiddleware({
      pipelineId: 'web',
      client: mockClient,
      exclude: ['/health', '/readyz'],
      maxBufferSize: 1,
    });

    const req = createMockReq({ originalUrl: '/health' });
    const res = createMockRes();
    const next = vi.fn();

    middleware(req, res, next);
    res.emit('finish');

    await vi.advanceTimersByTimeAsync(5000);

    // Should not have ingested the excluded path
    expect(mockClient.ingest).not.toHaveBeenCalled();
    expect(next).toHaveBeenCalledTimes(1);
  });

  it('excludes paths matching RegExp', async () => {
    const middleware = streamforgeMiddleware({
      pipelineId: 'web',
      client: mockClient,
      exclude: [/^\/internal\//],
      maxBufferSize: 1,
    });

    const req = createMockReq({ originalUrl: '/internal/debug' });
    const res = createMockRes();
    const next = vi.fn();

    middleware(req, res, next);
    res.emit('finish');

    await vi.advanceTimersByTimeAsync(5000);

    expect(mockClient.ingest).not.toHaveBeenCalled();
  });

  it('does not exclude non-matching paths', async () => {
    const middleware = streamforgeMiddleware({
      pipelineId: 'web',
      client: mockClient,
      exclude: ['/health'],
      maxBufferSize: 1,
    });

    const req = createMockReq({ originalUrl: '/api/data' });
    const res = createMockRes();
    const next = vi.fn();

    middleware(req, res, next);
    res.emit('finish');

    await vi.advanceTimersByTimeAsync(0);

    expect(mockClient.ingest).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// Transform
// ---------------------------------------------------------------------------

describe('Transform function', () => {
  let mockClient: ReturnType<typeof createMockClient>;

  beforeEach(() => {
    mockClient = createMockClient();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('modifies events via transform', async () => {
    const middleware = streamforgeMiddleware({
      pipelineId: 'web',
      client: mockClient,
      maxBufferSize: 1,
      transform: (event) => ({
        ...event,
        customField: 'added',
      }),
    });

    const req = createMockReq();
    const res = createMockRes();
    const next = vi.fn();

    middleware(req, res, next);
    res.emit('finish');

    await vi.advanceTimersByTimeAsync(0);

    const events = (mockClient.ingest as any).mock.calls[0][1];
    expect(events[0].customField).toBe('added');
  });

  it('skips event when transform returns null', async () => {
    const middleware = streamforgeMiddleware({
      pipelineId: 'web',
      client: mockClient,
      flushInterval: 100,
      maxBufferSize: 100,
      transform: () => null,
    });

    const req = createMockReq();
    const res = createMockRes();
    const next = vi.fn();

    middleware(req, res, next);
    res.emit('finish');

    // Advance past flush interval
    await vi.advanceTimersByTimeAsync(200);

    // Buffer should be empty, so no ingest call (flush skips empty buffer)
    expect(mockClient.ingest).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Error handling (silent)
// ---------------------------------------------------------------------------

describe('Error handling', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('silently drops events when ingest fails', async () => {
    const failingClient = {
      ingest: vi.fn().mockRejectedValue(new Error('Network error')),
    } as unknown as StreamForge;

    const middleware = streamforgeMiddleware({
      pipelineId: 'web',
      client: failingClient,
      maxBufferSize: 1,
    });

    const req = createMockReq();
    const res = createMockRes();
    const next = vi.fn();

    // Should not throw
    middleware(req, res, next);
    res.emit('finish');

    await vi.advanceTimersByTimeAsync(0);

    expect(failingClient.ingest).toHaveBeenCalledTimes(1);
    // The middleware should not throw — request handling continues normally
    expect(next).toHaveBeenCalledTimes(1);
  });

  it('always calls next() even if buffer logic has issues', () => {
    const middleware = streamforgeMiddleware({
      pipelineId: 'web',
      client: createMockClient(),
    });

    const req = createMockReq();
    const res = createMockRes();
    const next = vi.fn();

    middleware(req, res, next);
    expect(next).toHaveBeenCalledTimes(1);
  });
});
