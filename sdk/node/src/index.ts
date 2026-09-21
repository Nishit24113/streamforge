// StreamForge Node.js/TypeScript SDK
// Serverless real-time data pipeline platform client

// ---------------------------------------------------------------------------
// Types & Interfaces
// ---------------------------------------------------------------------------

export interface StreamForgeConfig {
  /** Base URL for the ingestion / pipeline API */
  apiUrl: string;
  /** Base URL for the analytics API (defaults to apiUrl) */
  analyticsUrl?: string;
  /** API key for authentication */
  apiKey?: string;
  /** Organisation ID for multi-tenant isolation */
  orgId?: string;
  /** Maximum retry attempts (default 3) */
  maxRetries?: number;
  /** Base delay in ms for exponential backoff (default 500) */
  retryBaseDelay?: number;
}

export interface PipelineConfig {
  name: string;
  description?: string;
  schema?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface Pipeline {
  id: string;
  name: string;
  description?: string;
  status?: string;
  createdAt?: string;
  [key: string]: unknown;
}

export interface PipelineRun {
  id: string;
  pipelineId: string;
  status: string;
  startedAt?: string;
  completedAt?: string;
  [key: string]: unknown;
}

export interface IngestResponse {
  accepted: number;
  [key: string]: unknown;
}

export interface QueryResult {
  id: string;
  status: string;
  rows?: Record<string, unknown>[];
  columns?: string[];
  [key: string]: unknown;
}

export interface PipelineStats {
  [key: string]: unknown;
}

export interface Anomaly {
  timestamp: string;
  pipelineId?: string;
  severity?: string;
  message?: string;
  [key: string]: unknown;
}

export interface UploadResponse {
  uploadUrl: string;
  [key: string]: unknown;
}

export interface HealthStatus {
  status: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

export class StreamForgeError extends Error {
  public readonly statusCode: number | undefined;
  public readonly responseBody: unknown;

  constructor(message: string, statusCode?: number, responseBody?: unknown) {
    super(message);
    this.name = 'StreamForgeError';
    this.statusCode = statusCode;
    this.responseBody = responseBody;
  }
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export class StreamForge {
  private readonly apiUrl: string;
  private readonly analyticsUrl: string;
  private readonly apiKey: string | undefined;
  private readonly orgId: string | undefined;
  private readonly maxRetries: number;
  private readonly retryBaseDelay: number;

  constructor(config: StreamForgeConfig) {
    this.apiUrl = config.apiUrl.replace(/\/+$/, '');
    this.analyticsUrl = (config.analyticsUrl ?? config.apiUrl).replace(/\/+$/, '');
    this.apiKey = config.apiKey;
    this.orgId = config.orgId;
    this.maxRetries = config.maxRetries ?? 3;
    this.retryBaseDelay = config.retryBaseDelay ?? 500;
  }

  // -----------------------------------------------------------------------
  // Ingestion
  // -----------------------------------------------------------------------

  /** Send an array of events to a pipeline. */
  async ingest(pipelineId: string, events: Record<string, unknown>[]): Promise<IngestResponse> {
    return this.request<IngestResponse>('POST', `${this.apiUrl}/ingest`, {
      pipeline: pipelineId,
      events,
    });
  }

  /**
   * Batch-send a large list of events, splitting into chunks of `batchSize`.
   * Returns the aggregated count of accepted events.
   */
  async ingestBatch(
    pipelineId: string,
    events: Record<string, unknown>[],
    batchSize = 500,
  ): Promise<{ accepted: number }> {
    let totalAccepted = 0;

    for (let i = 0; i < events.length; i += batchSize) {
      const chunk = events.slice(i, i + batchSize);
      const res = await this.ingest(pipelineId, chunk);
      totalAccepted += res.accepted ?? chunk.length;
    }

    return { accepted: totalAccepted };
  }

  // -----------------------------------------------------------------------
  // Pipelines
  // -----------------------------------------------------------------------

  /** Create a new pipeline. */
  async createPipeline(config: PipelineConfig): Promise<Pipeline> {
    return this.request<Pipeline>('POST', `${this.apiUrl}/pipelines`, config);
  }

  /** List all pipelines. */
  async listPipelines(): Promise<Pipeline[]> {
    return this.request<Pipeline[]>('GET', `${this.apiUrl}/pipelines`);
  }

  /** Get a single pipeline by ID. */
  async getPipeline(pipelineId: string): Promise<Pipeline> {
    return this.request<Pipeline>('GET', `${this.apiUrl}/pipelines/${encodeURIComponent(pipelineId)}`);
  }

  /** Get run history for a pipeline. */
  async getRuns(pipelineId: string): Promise<PipelineRun[]> {
    return this.request<PipelineRun[]>(
      'GET',
      `${this.apiUrl}/pipelines/${encodeURIComponent(pipelineId)}/runs`,
    );
  }

  // -----------------------------------------------------------------------
  // File upload
  // -----------------------------------------------------------------------

  /**
   * Upload a file to a pipeline via a presigned URL.
   *
   * 1. Requests a presigned upload URL from the API.
   * 2. Reads the local file and PUTs its contents to the presigned URL.
   */
  async uploadFile(pipelineId: string, filepath: string): Promise<UploadResponse> {
    const { readFile } = await import('node:fs/promises');
    const { basename } = await import('node:path');

    const filename = basename(filepath);
    const uploadMeta = await this.request<UploadResponse>('POST', `${this.apiUrl}/upload`, {
      pipeline: pipelineId,
      filename,
    });

    const fileBuffer = await readFile(filepath);

    const putRes = await fetch(uploadMeta.uploadUrl, {
      method: 'PUT',
      body: fileBuffer,
      headers: { 'Content-Type': 'application/octet-stream' },
    });

    if (!putRes.ok) {
      throw new StreamForgeError(
        `File upload PUT failed: ${putRes.status} ${putRes.statusText}`,
        putRes.status,
      );
    }

    return uploadMeta;
  }

  // -----------------------------------------------------------------------
  // Analytics
  // -----------------------------------------------------------------------

  /**
   * Run a SQL query against the analytics API.
   * Automatically polls until the query completes or fails.
   */
  async query(sql: string): Promise<QueryResult> {
    const submitted = await this.request<QueryResult>(
      'POST',
      `${this.analyticsUrl}/query`,
      { sql },
    );

    // If the result is already complete, return immediately.
    if (submitted.status === 'completed' || submitted.rows) {
      return submitted;
    }

    // Poll for completion.
    const queryId = submitted.id;
    const maxPollAttempts = 60;
    const pollInterval = 1000; // 1 second

    for (let attempt = 0; attempt < maxPollAttempts; attempt++) {
      await this.sleep(pollInterval);

      const result = await this.request<QueryResult>(
        'GET',
        `${this.analyticsUrl}/query/${encodeURIComponent(queryId)}`,
      );

      if (result.status === 'completed' || result.rows) {
        return result;
      }

      if (result.status === 'failed' || result.status === 'error') {
        throw new StreamForgeError(`Query ${queryId} failed`, undefined, result);
      }
    }

    throw new StreamForgeError(`Query ${queryId} timed out after ${maxPollAttempts}s`);
  }

  /** Get pipeline statistics. */
  async getStats(): Promise<PipelineStats> {
    return this.request<PipelineStats>('GET', `${this.analyticsUrl}/stats`);
  }

  /** Get anomaly timeline, optionally filtered to a specific pipeline. */
  async getAnomalies(pipelineId?: string): Promise<Anomaly[]> {
    const url = new URL(`${this.analyticsUrl}/anomalies`);
    if (pipelineId) {
      url.searchParams.set('pipelineId', pipelineId);
    }
    return this.request<Anomaly[]>('GET', url.toString());
  }

  // -----------------------------------------------------------------------
  // Health
  // -----------------------------------------------------------------------

  /** Health check. */
  async health(): Promise<HealthStatus> {
    return this.request<HealthStatus>('GET', `${this.apiUrl}/health`);
  }

  // -----------------------------------------------------------------------
  // Internal helpers
  // -----------------------------------------------------------------------

  private buildHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    };

    if (this.apiKey) {
      headers['Authorization'] = `Bearer ${this.apiKey}`;
    }

    if (this.orgId) {
      headers['X-Org-Id'] = this.orgId;
    }

    return headers;
  }

  private async request<T>(method: string, url: string, body?: unknown): Promise<T> {
    let lastError: unknown;

    for (let attempt = 0; attempt < this.maxRetries; attempt++) {
      try {
        const res = await fetch(url, {
          method,
          headers: this.buildHeaders(),
          body: body !== undefined ? JSON.stringify(body) : undefined,
        });

        if (!res.ok) {
          const text = await res.text().catch(() => '');
          let parsed: unknown;
          try {
            parsed = JSON.parse(text);
          } catch {
            parsed = text;
          }

          // Don't retry 4xx client errors (except 429 Too Many Requests).
          if (res.status >= 400 && res.status < 500 && res.status !== 429) {
            throw new StreamForgeError(
              `${method} ${url} returned ${res.status}`,
              res.status,
              parsed,
            );
          }

          throw new StreamForgeError(
            `${method} ${url} returned ${res.status}`,
            res.status,
            parsed,
          );
        }

        return (await res.json()) as T;
      } catch (err) {
        lastError = err;

        // Non-retryable client errors bubble up immediately.
        if (err instanceof StreamForgeError && err.statusCode && err.statusCode >= 400 && err.statusCode < 500 && err.statusCode !== 429) {
          throw err;
        }

        // Exponential backoff before next attempt.
        if (attempt < this.maxRetries - 1) {
          const delay = this.retryBaseDelay * Math.pow(2, attempt);
          await this.sleep(delay);
        }
      }
    }

    if (lastError instanceof StreamForgeError) {
      throw lastError;
    }
    throw new StreamForgeError(
      `${method} ${url} failed after ${this.maxRetries} attempts: ${lastError}`,
    );
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

export default StreamForge;
