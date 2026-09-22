import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createTestQueryClient } from './setup';
import App from '../App';

// Mock API module
vi.mock('../utils/api', () => ({
  checkHealth: vi.fn().mockResolvedValue({ status: 'healthy', service: 'streamforge' }),
  getStats: vi.fn().mockResolvedValue({
    total_events: 247893,
    total_anomalies: 1247,
    total_runs: 892,
    completed_runs: 856,
    failed_runs: 12,
    active_pipelines: 3,
    anomaly_rate: 0.5,
    pipeline_stats: {},
  }),
}));

// Mock child components to isolate App tests
vi.mock('../components/Overview', () => ({
  default: ({ stats }) => <div data-testid="overview-view">Overview Component</div>,
}));
vi.mock('../components/PipelineMonitor', () => ({
  default: () => <div data-testid="pipeline-view">Pipeline Component</div>,
}));
vi.mock('../components/AnomalyTimeline', () => ({
  default: () => <div data-testid="anomaly-view">Anomaly Component</div>,
}));
vi.mock('../components/DataExplorer', () => ({
  default: () => <div data-testid="explorer-view">Explorer Component</div>,
}));
vi.mock('../components/QueryEditor', () => ({
  default: () => <div data-testid="query-view">Query Component</div>,
}));

function renderApp() {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  );
}

describe('App', () => {
  it('renders sidebar with all 5 navigation items', () => {
    renderApp();
    // Nav labels appear in the sidebar buttons
    const navButtons = screen.getAllByRole('button').filter(
      (btn) => btn.closest('nav')
    );
    expect(navButtons.length).toBe(5);
    // Each label appears at least once (also in header for active view)
    expect(screen.getAllByText('Overview').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Pipelines')).toBeInTheDocument();
    expect(screen.getByText('Anomalies')).toBeInTheDocument();
    expect(screen.getByText('Data Explorer')).toBeInTheDocument();
    expect(screen.getByText('SQL Query')).toBeInTheDocument();
  });

  it('renders the StreamForge brand name', () => {
    renderApp();
    expect(screen.getByText('StreamForge')).toBeInTheDocument();
  });

  it('shows Overview as the default active view', () => {
    renderApp();
    expect(screen.getByTestId('overview-view')).toBeInTheDocument();
  });

  it('switches to Pipelines view on nav click', () => {
    renderApp();
    fireEvent.click(screen.getByText('Pipelines'));
    expect(screen.getByTestId('pipeline-view')).toBeInTheDocument();
    expect(screen.queryByTestId('overview-view')).not.toBeInTheDocument();
  });

  it('switches to Anomalies view on nav click', () => {
    renderApp();
    fireEvent.click(screen.getByText('Anomalies'));
    expect(screen.getByTestId('anomaly-view')).toBeInTheDocument();
  });

  it('switches to Data Explorer view on nav click', () => {
    renderApp();
    fireEvent.click(screen.getByText('Data Explorer'));
    expect(screen.getByTestId('explorer-view')).toBeInTheDocument();
  });

  it('switches to SQL Query view on nav click', () => {
    renderApp();
    fireEvent.click(screen.getByText('SQL Query'));
    expect(screen.getByTestId('query-view')).toBeInTheDocument();
  });

  it('renders health status indicator', async () => {
    renderApp();
    await waitFor(() => {
      expect(screen.getByText('System Healthy')).toBeInTheDocument();
    });
  });

  it('renders active pipelines count from stats', async () => {
    renderApp();
    await waitFor(() => {
      expect(screen.getByText('3 active pipelines')).toBeInTheDocument();
    });
  });

  it('displays total event count in header', async () => {
    renderApp();
    await waitFor(() => {
      expect(screen.getByText('247,893 events')).toBeInTheDocument();
    });
  });
});
