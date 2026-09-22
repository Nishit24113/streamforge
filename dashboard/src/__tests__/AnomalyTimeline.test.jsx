import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { createTestQueryClient } from './setup';
import AnomalyTimeline from '../components/AnomalyTimeline';

const now = Date.now();

const mockAnomalies = {
  anomalies: [
    { pipeline_id: 'ecommerce-events', alert_id: 'alert-001', event_type: 'purchase', anomaly_score: '0.9234', severity: 'HIGH', timestamp: now - 1800000, created_at: now / 1000 - 1800 },
    { pipeline_id: 'iot-sensors', alert_id: 'alert-002', event_type: 'temperature', anomaly_score: '0.7812', severity: 'MEDIUM', timestamp: now - 3600000, created_at: now / 1000 - 3600 },
    { pipeline_id: 'web-analytics', alert_id: 'alert-003', event_type: 'page_view', anomaly_score: '0.8567', severity: 'HIGH', timestamp: now - 5400000, created_at: now / 1000 - 5400 },
    { pipeline_id: 'ecommerce-events', alert_id: 'alert-004', event_type: 'purchase', anomaly_score: '0.6543', severity: 'MEDIUM', timestamp: now - 7200000, created_at: now / 1000 - 7200 },
    { pipeline_id: 'iot-sensors', alert_id: 'alert-005', event_type: 'temperature', anomaly_score: '0.9101', severity: 'HIGH', timestamp: now - 9000000, created_at: now / 1000 - 9000 },
  ],
  count: 5,
};

vi.mock('../utils/api', () => ({
  getAnomalies: vi.fn().mockResolvedValue({
    anomalies: [
      { pipeline_id: 'ecommerce-events', alert_id: 'alert-001', event_type: 'purchase', anomaly_score: '0.9234', severity: 'HIGH', timestamp: Date.now() - 1800000, created_at: Date.now() / 1000 - 1800 },
      { pipeline_id: 'iot-sensors', alert_id: 'alert-002', event_type: 'temperature', anomaly_score: '0.7812', severity: 'MEDIUM', timestamp: Date.now() - 3600000, created_at: Date.now() / 1000 - 3600 },
      { pipeline_id: 'web-analytics', alert_id: 'alert-003', event_type: 'page_view', anomaly_score: '0.8567', severity: 'HIGH', timestamp: Date.now() - 5400000, created_at: Date.now() / 1000 - 5400 },
      { pipeline_id: 'ecommerce-events', alert_id: 'alert-004', event_type: 'purchase', anomaly_score: '0.6543', severity: 'MEDIUM', timestamp: Date.now() - 7200000, created_at: Date.now() / 1000 - 7200 },
      { pipeline_id: 'iot-sensors', alert_id: 'alert-005', event_type: 'temperature', anomaly_score: '0.9101', severity: 'HIGH', timestamp: Date.now() - 9000000, created_at: Date.now() / 1000 - 9000 },
    ],
    count: 5,
  }),
}));

function renderAnomalyTimeline() {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <AnomalyTimeline />
    </QueryClientProvider>
  );
}

describe('AnomalyTimeline', () => {
  it('renders summary card labels', async () => {
    renderAnomalyTimeline();
    await waitFor(() => {
      expect(screen.getByText('Total Anomalies')).toBeInTheDocument();
    });
    expect(screen.getByText('High Severity')).toBeInTheDocument();
    expect(screen.getByText('Medium Severity')).toBeInTheDocument();
    expect(screen.getByText('Avg Score')).toBeInTheDocument();
  });

  it('shows correct total anomaly count', async () => {
    renderAnomalyTimeline();
    await waitFor(() => {
      // The "5" for total anomalies
      const totalCard = screen.getByText('Total Anomalies').closest('div[class*="glass-card"]');
      expect(totalCard).toHaveTextContent('5');
    });
  });

  it('shows correct high severity count', async () => {
    renderAnomalyTimeline();
    await waitFor(() => {
      const highCard = screen.getByText('High Severity').closest('div[class*="glass-card"]');
      expect(highCard).toHaveTextContent('3'); // 3 HIGH anomalies
    });
  });

  it('shows correct medium severity count', async () => {
    renderAnomalyTimeline();
    await waitFor(() => {
      const medCard = screen.getByText('Medium Severity').closest('div[class*="glass-card"]');
      expect(medCard).toHaveTextContent('2'); // 2 MEDIUM anomalies
    });
  });

  it('renders pipeline filter dropdown', async () => {
    renderAnomalyTimeline();
    const select = screen.getByDisplayValue('All Pipelines');
    expect(select).toBeInTheDocument();
    expect(select.tagName).toBe('SELECT');
  });

  it('pipeline filter dropdown has all options', () => {
    renderAnomalyTimeline();
    const select = screen.getByDisplayValue('All Pipelines');
    const options = select.querySelectorAll('option');
    expect(options.length).toBe(4); // All + 3 pipelines
  });

  it('allows selecting a specific pipeline filter', () => {
    renderAnomalyTimeline();
    const select = screen.getByDisplayValue('All Pipelines');
    fireEvent.change(select, { target: { value: 'ecommerce-events' } });
    expect(select.value).toBe('ecommerce-events');
  });

  it('renders anomaly list items with event types', async () => {
    renderAnomalyTimeline();
    await waitFor(() => {
      expect(screen.getAllByText('purchase').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('temperature').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('page_view')).toBeInTheDocument();
    });
  });

  it('renders severity badges on anomaly items', async () => {
    renderAnomalyTimeline();
    await waitFor(() => {
      const highBadges = screen.getAllByText('HIGH');
      const medBadges = screen.getAllByText('MEDIUM');
      expect(highBadges.length).toBeGreaterThanOrEqual(1);
      expect(medBadges.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders anomaly score values', async () => {
    renderAnomalyTimeline();
    await waitFor(() => {
      expect(screen.getByText('0.9234')).toBeInTheDocument();
      expect(screen.getByText('0.7812')).toBeInTheDocument();
    });
  });

  it('renders the Anomaly Score Timeline chart title', async () => {
    renderAnomalyTimeline();
    expect(screen.getByText('Anomaly Score Timeline')).toBeInTheDocument();
  });

  it('renders the Recent Anomalies section header', () => {
    renderAnomalyTimeline();
    expect(screen.getByText('Recent Anomalies')).toBeInTheDocument();
  });
});
