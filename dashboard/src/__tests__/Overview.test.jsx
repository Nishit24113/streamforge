import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import Overview from '../components/Overview';

const mockStats = {
  total_events: 247893,
  total_anomalies: 1247,
  total_runs: 892,
  completed_runs: 856,
  failed_runs: 12,
  active_pipelines: 3,
  anomaly_rate: 0.5,
};

describe('Overview', () => {
  it('renders all 6 stat card labels', () => {
    render(<Overview stats={mockStats} />);
    expect(screen.getByText('Total Events')).toBeInTheDocument();
    expect(screen.getByText('Pipeline Runs')).toBeInTheDocument();
    expect(screen.getByText('Anomalies Detected')).toBeInTheDocument();
    expect(screen.getByText('Success Rate')).toBeInTheDocument();
    expect(screen.getByText('Failed Runs')).toBeInTheDocument();
    expect(screen.getByText('Anomaly Rate')).toBeInTheDocument();
  });

  it('renders correct stat values from props', () => {
    render(<Overview stats={mockStats} />);
    expect(screen.getByText('247,893')).toBeInTheDocument();
    expect(screen.getByText('892')).toBeInTheDocument();
    expect(screen.getByText('1,247')).toBeInTheDocument();
    expect(screen.getByText('96.0%')).toBeInTheDocument(); // (856/892)*100 = 95.96 -> 96.0
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('0.5%')).toBeInTheDocument();
  });

  it('handles null stats gracefully with defaults', () => {
    render(<Overview stats={null} />);
    // Defaults kick in
    expect(screen.getByText('247,893')).toBeInTheDocument();
    expect(screen.getByText('Total Events')).toBeInTheDocument();
  });

  it('handles undefined stats gracefully', () => {
    render(<Overview />);
    expect(screen.getByText('Total Events')).toBeInTheDocument();
    expect(screen.getByText('892')).toBeInTheDocument();
  });

  it('shows 99.9% success rate when total_runs is 0', () => {
    const zeroRunStats = { ...mockStats, total_runs: 0, completed_runs: 0, failed_runs: 0 };
    render(<Overview stats={zeroRunStats} />);
    expect(screen.getByText('99.9%')).toBeInTheDocument();
  });

  it('renders chart section titles', () => {
    render(<Overview stats={mockStats} />);
    expect(screen.getByText('Event Throughput (24h)')).toBeInTheDocument();
    expect(screen.getByText('Pipeline Throughput')).toBeInTheDocument();
    expect(screen.getByText('Processing Latency (ms)')).toBeInTheDocument();
    expect(screen.getByText('Anomaly Severity')).toBeInTheDocument();
  });

  it('renders latency legend items (p50, p95, p99)', () => {
    render(<Overview stats={mockStats} />);
    expect(screen.getByText('p50')).toBeInTheDocument();
    expect(screen.getByText('p95')).toBeInTheDocument();
    expect(screen.getByText('p99')).toBeInTheDocument();
  });

  it('renders anomaly distribution legend entries', () => {
    render(<Overview stats={mockStats} />);
    expect(screen.getByText(/High/)).toBeInTheDocument();
    expect(screen.getByText(/Medium/)).toBeInTheDocument();
    expect(screen.getByText(/Low/)).toBeInTheDocument();
  });
});
