import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import QueryEditor from '../components/QueryEditor';

vi.mock('../utils/api', () => ({
  runQuery: vi.fn().mockResolvedValue({
    status: 'completed',
    query_id: 'q-test123',
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
  }),
  getQueryResults: vi.fn().mockResolvedValue({
    status: 'completed',
    query_id: 'q-test123',
    columns: ['event_type', 'event_count'],
    rows: [{ event_type: 'purchase', event_count: '1247' }],
    row_count: 1,
    bytes_scanned: 524288,
    execution_time_ms: 1200,
  }),
}));

describe('QueryEditor', () => {
  it('renders the SQL textarea', () => {
    render(<QueryEditor />);
    const textarea = screen.getByPlaceholderText(/SELECT \* FROM/);
    expect(textarea).toBeInTheDocument();
    expect(textarea.tagName).toBe('TEXTAREA');
  });

  it('textarea has the first sample query pre-populated', () => {
    render(<QueryEditor />);
    const textarea = screen.getByPlaceholderText(/SELECT \* FROM/);
    expect(textarea.value).toContain('event_type');
    expect(textarea.value).toContain('COUNT(*)');
  });

  it('renders all 4 sample query buttons', () => {
    render(<QueryEditor />);
    expect(screen.getByText('Event Count by Type')).toBeInTheDocument();
    expect(screen.getByText('Anomaly Summary')).toBeInTheDocument();
    expect(screen.getByText('Hourly Throughput')).toBeInTheDocument();
    expect(screen.getByText('Top Sources')).toBeInTheDocument();
  });

  it('clicking sample query button populates textarea', async () => {
    render(<QueryEditor />);
    fireEvent.click(screen.getByText('Anomaly Summary'));
    const textarea = screen.getByPlaceholderText(/SELECT \* FROM/);
    expect(textarea.value).toContain('anomaly_score');
  });

  it('clicking Hourly Throughput populates the correct query', () => {
    render(<QueryEditor />);
    fireEvent.click(screen.getByText('Hourly Throughput'));
    const textarea = screen.getByPlaceholderText(/SELECT \* FROM/);
    expect(textarea.value).toContain('DATE_FORMAT');
    expect(textarea.value).toContain('pipeline_id');
  });

  it('accepts user input in the textarea', () => {
    render(<QueryEditor />);
    const textarea = screen.getByPlaceholderText(/SELECT \* FROM/);
    fireEvent.change(textarea, { target: { value: 'SELECT 1' } });
    expect(textarea.value).toBe('SELECT 1');
  });

  it('renders Run Query button', () => {
    render(<QueryEditor />);
    expect(screen.getByText('Run Query')).toBeInTheDocument();
  });

  it('renders SQL Editor label', () => {
    render(<QueryEditor />);
    expect(screen.getByText('SQL Editor')).toBeInTheDocument();
  });

  it('shows results table after running query', async () => {
    render(<QueryEditor />);
    fireEvent.click(screen.getByText('Run Query'));

    await waitFor(() => {
      expect(screen.getByText('4 rows')).toBeInTheDocument();
    });

    // Column headers
    expect(screen.getByText('event_type')).toBeInTheDocument();
    expect(screen.getByText('event_count')).toBeInTheDocument();
    expect(screen.getByText('event_date')).toBeInTheDocument();

    // Row data
    expect(screen.getByText('purchase')).toBeInTheDocument();
    expect(screen.getByText('8923')).toBeInTheDocument();
  });

  it('shows execution metadata after query', async () => {
    render(<QueryEditor />);
    fireEvent.click(screen.getByText('Run Query'));

    await waitFor(() => {
      expect(screen.getByText('2340ms')).toBeInTheDocument();
      expect(screen.getByText('1.00 MB scanned')).toBeInTheDocument();
    });
  });

  it('renders Copy CSV button after results', async () => {
    render(<QueryEditor />);
    fireEvent.click(screen.getByText('Run Query'));

    await waitFor(() => {
      expect(screen.getByText('Copy CSV')).toBeInTheDocument();
    });
  });

  it('copies CSV to clipboard when Copy CSV is clicked', async () => {
    render(<QueryEditor />);
    fireEvent.click(screen.getByText('Run Query'));

    await waitFor(() => {
      expect(screen.getByText('Copy CSV')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Copy CSV'));

    expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    const csvArg = navigator.clipboard.writeText.mock.calls[0][0];
    expect(csvArg).toContain('event_type,event_count,event_date');
    expect(csvArg).toContain('purchase,1247,2026-09-18');
  });
});
