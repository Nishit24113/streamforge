import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { createTestQueryClient } from './setup';
import PipelineMonitor from '../components/PipelineMonitor';

const mockPipelines = {
  pipelines: [
    { pipeline_id: 'ecommerce-events', name: 'E-Commerce Events', status: 'ACTIVE', created_at: Date.now() / 1000 - 86400 },
    { pipeline_id: 'iot-sensors', name: 'IoT Sensor Data', status: 'ACTIVE', created_at: Date.now() / 1000 - 86400 * 2 },
    { pipeline_id: 'web-analytics', name: 'Web Analytics', status: 'ACTIVE', created_at: Date.now() / 1000 - 86400 * 3 },
  ],
  count: 3,
};

const mockRuns = {
  pipeline_id: 'ecommerce-events',
  runs: [
    { pipeline_id: 'ecommerce-events', run_id: 'run-abc123', status: 'COMPLETED', started_at: Date.now() / 1000 - 3600, events_count: 250, anomaly_count: 3 },
    { pipeline_id: 'ecommerce-events', run_id: 'run-def456', status: 'PROCESSING', started_at: Date.now() / 1000 - 7200, events_count: 180, anomaly_count: 0 },
    { pipeline_id: 'ecommerce-events', run_id: 'run-ghi789', status: 'FAILED', started_at: Date.now() / 1000 - 10800, events_count: 100, anomaly_count: 1 },
  ],
  count: 3,
};

const mockIngestResult = {
  status: 'accepted',
  pipeline: 'ecommerce-events',
  run_id: 'run-test123',
  events_received: 10,
  events_failed: 0,
};

vi.mock('../utils/api', () => ({
  listPipelines: vi.fn().mockResolvedValue({
    pipelines: [
      { pipeline_id: 'ecommerce-events', name: 'E-Commerce Events', status: 'ACTIVE', created_at: Date.now() / 1000 - 86400 },
      { pipeline_id: 'iot-sensors', name: 'IoT Sensor Data', status: 'ACTIVE', created_at: Date.now() / 1000 - 86400 * 2 },
      { pipeline_id: 'web-analytics', name: 'Web Analytics', status: 'ACTIVE', created_at: Date.now() / 1000 - 86400 * 3 },
    ],
    count: 3,
  }),
  getPipelineRuns: vi.fn().mockResolvedValue({
    pipeline_id: 'ecommerce-events',
    runs: [
      { pipeline_id: 'ecommerce-events', run_id: 'run-abc123', status: 'COMPLETED', started_at: Date.now() / 1000 - 3600, events_count: 250, anomaly_count: 3 },
      { pipeline_id: 'ecommerce-events', run_id: 'run-def456', status: 'PROCESSING', started_at: Date.now() / 1000 - 7200, events_count: 180, anomaly_count: 0 },
    ],
    count: 2,
  }),
  ingestEvents: vi.fn().mockResolvedValue({
    status: 'accepted',
    pipeline: 'ecommerce-events',
    run_id: 'run-test123',
    events_received: 10,
    events_failed: 0,
  }),
}));

function renderPipelineMonitor() {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <PipelineMonitor />
    </QueryClientProvider>
  );
}

describe('PipelineMonitor', () => {
  it('renders pipeline list after loading', async () => {
    renderPipelineMonitor();
    await waitFor(() => {
      expect(screen.getByText('E-Commerce Events')).toBeInTheDocument();
    });
    expect(screen.getByText('IoT Sensor Data')).toBeInTheDocument();
    // "Web Analytics" appears in both select dropdown and pipeline card
    expect(screen.getAllByText('Web Analytics').length).toBeGreaterThanOrEqual(2);
  });

  it('shows pipeline count in section header', async () => {
    renderPipelineMonitor();
    await waitFor(() => {
      expect(screen.getByText('Pipelines (3)')).toBeInTheDocument();
    });
  });

  it('displays pipeline IDs as subtitles', async () => {
    renderPipelineMonitor();
    await waitFor(() => {
      expect(screen.getByText('ecommerce-events')).toBeInTheDocument();
      expect(screen.getByText('iot-sensors')).toBeInTheDocument();
      expect(screen.getByText('web-analytics')).toBeInTheDocument();
    });
  });

  it('renders ACTIVE status badges for all pipelines', async () => {
    renderPipelineMonitor();
    await waitFor(() => {
      const badges = screen.getAllByText('ACTIVE');
      expect(badges.length).toBe(3);
    });
  });

  it('expands pipeline card to show runs on click', async () => {
    renderPipelineMonitor();
    await waitFor(() => {
      expect(screen.getByText('E-Commerce Events')).toBeInTheDocument();
    });

    // Click the pipeline card button to expand
    const pipelineButton = screen.getByText('E-Commerce Events').closest('button');
    fireEvent.click(pipelineButton);

    await waitFor(() => {
      expect(screen.getByText('Recent Runs')).toBeInTheDocument();
    });
  });

  it('shows run status badges after expanding', async () => {
    renderPipelineMonitor();
    await waitFor(() => {
      expect(screen.getByText('E-Commerce Events')).toBeInTheDocument();
    });

    const pipelineButton = screen.getByText('E-Commerce Events').closest('button');
    fireEvent.click(pipelineButton);

    await waitFor(() => {
      expect(screen.getByText('COMPLETED')).toBeInTheDocument();
      expect(screen.getByText('PROCESSING')).toBeInTheDocument();
    });
  });

  it('renders Send Test Data section', async () => {
    renderPipelineMonitor();
    expect(screen.getByText('Send Test Data')).toBeInTheDocument();
  });

  it('renders pipeline select dropdown in Send Test Data', () => {
    renderPipelineMonitor();
    const select = screen.getByDisplayValue('E-Commerce');
    expect(select).toBeInTheDocument();
    expect(select.tagName).toBe('SELECT');
  });

  it('allows changing pipeline in Send Test Data', async () => {
    renderPipelineMonitor();
    const select = screen.getByDisplayValue('E-Commerce');
    fireEvent.change(select, { target: { value: 'iot-sensors' } });
    expect(select.value).toBe('iot-sensors');
  });

  it('renders event count input with default value 10', () => {
    renderPipelineMonitor();
    const input = screen.getByDisplayValue('10');
    expect(input).toBeInTheDocument();
    expect(input.type).toBe('number');
  });

  it('renders Send button', () => {
    renderPipelineMonitor();
    expect(screen.getByText('Send')).toBeInTheDocument();
  });
});
