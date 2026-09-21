// StreamForge Express / Fastify middleware
// Auto-captures HTTP request/response events and ingests them into a pipeline.

import { StreamForge, type StreamForgeConfig } from './index.js';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface MiddlewareOptions {
  /** Pipeline ID to send captured events to. */
  pipelineId: string;
  /** StreamForge API URL (required if no `client` is provided). */
  apiUrl?: string;
  /** Pre-configured StreamForge client (takes precedence over apiUrl/apiKey/orgId). */
  client?: StreamForge;
  /** API key forwarded to the StreamForge client. */
  apiKey?: string;
  /** Org ID forwarded to the StreamForge client. */
  orgId?: string;
  /** Paths to exclude from capture (exact match or RegExp). */
  exclude?: (string | RegExp)[];
  /**
   * Optional transform applied to the event before ingestion.
   * Return `null` to skip the event.
   */
  transform?: (event: RequestEvent) => RequestEvent | null;
  /**
   * Flush interval in ms. Events are buffered and sent in batches.
   * Default: 5000 (5 seconds).
   */
  flushInterval?: number;
  /** Maximum buffer size before an automatic flush. Default: 100. */
  maxBufferSize?: number;
}

export interface RequestEvent {
  method: string;
  path: string;
  statusCode: number;
  durationMs: number;
  userAgent?: string;
  ip?: string;
  timestamp: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Middleware factory
// ---------------------------------------------------------------------------

/**
 * Creates an Express-compatible middleware that captures HTTP request/response
 * metrics and ingests them into a StreamForge pipeline.
 *
 * Usage:
 * ```ts
 * import express from 'express';
 * import { streamforgeMiddleware } from 'streamforge/middleware';
 *
 * const app = express();
 * app.use(streamforgeMiddleware({
 *   pipelineId: 'web-analytics',
 *   apiUrl: 'https://api.example.com',
 * }));
 * ```
 *
 * The returned function also works as a Fastify `onRequest` / `onResponse`
 * hook when wrapped with Fastify's middie or fastify-express plugin.
 */
export function streamforgeMiddleware(options: MiddlewareOptions) {
  const {
    pipelineId,
    exclude = [],
    transform,
    flushInterval = 5_000,
    maxBufferSize = 100,
  } = options;

  const client =
    options.client ??
    new StreamForge({
      apiUrl: options.apiUrl ?? '',
      apiKey: options.apiKey,
      orgId: options.orgId,
    });

  let buffer: Record<string, unknown>[] = [];
  let flushTimer: ReturnType<typeof setInterval> | null = null;

  // Start the periodic flush timer.
  const ensureTimer = () => {
    if (flushTimer === null) {
      flushTimer = setInterval(() => void flush(), flushInterval);
      // Allow the Node process to exit even if the timer is still active.
      if (typeof flushTimer === 'object' && 'unref' in flushTimer) {
        flushTimer.unref();
      }
    }
  };

  const flush = async () => {
    if (buffer.length === 0) return;

    const batch = buffer;
    buffer = [];

    try {
      await client.ingest(pipelineId, batch);
    } catch {
      // Silently drop on failure to avoid impacting request handling.
    }
  };

  const isExcluded = (path: string): boolean => {
    return exclude.some((pattern) => {
      if (typeof pattern === 'string') return path === pattern;
      return pattern.test(path);
    });
  };

  ensureTimer();

  // Express-style middleware signature: (req, res, next)
  return function streamforgeHandler(req: any, res: any, next: any) {
    const startTime = Date.now();
    const path: string = req.originalUrl ?? req.url ?? '';

    if (isExcluded(path)) {
      return next();
    }

    // Hook into the response finish event.
    const onFinish = () => {
      res.removeListener('finish', onFinish);

      let event: RequestEvent | null = {
        method: req.method,
        path,
        statusCode: res.statusCode,
        durationMs: Date.now() - startTime,
        userAgent: req.headers?.['user-agent'],
        ip: req.ip ?? req.socket?.remoteAddress,
        timestamp: new Date().toISOString(),
      };

      if (transform) {
        event = transform(event);
      }

      if (event) {
        buffer.push(event);

        if (buffer.length >= maxBufferSize) {
          void flush();
        }
      }
    };

    res.on('finish', onFinish);
    next();
  };
}

export default streamforgeMiddleware;
