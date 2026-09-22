import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import DataExplorer from '../components/DataExplorer';

describe('DataExplorer', () => {
  it('renders all three zone buttons (raw, clean, agg)', () => {
    render(<DataExplorer />);
    // Zone names appear in both the zone buttons (capitalized via class) and the s3 path
    expect(screen.getAllByText('raw').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('clean').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('agg').length).toBeGreaterThanOrEqual(1);
    // Verify the zone buttons themselves exist (with file counts and sizes)
    expect(screen.getByText('892 files')).toBeInTheDocument();   // raw
    expect(screen.getByText('852 files')).toBeInTheDocument();   // clean
    expect(screen.getByText('446 files')).toBeInTheDocument();   // agg
  });

  it('renders Three-Zone Data Lake Architecture heading', () => {
    render(<DataExplorer />);
    expect(screen.getByText('Three-Zone Data Lake Architecture')).toBeInTheDocument();
  });

  it('shows file counts for each zone', () => {
    render(<DataExplorer />);
    expect(screen.getByText('892 files')).toBeInTheDocument();   // raw total
    expect(screen.getByText('852 files')).toBeInTheDocument();   // clean total
    expect(screen.getByText('446 files')).toBeInTheDocument();   // agg total
  });

  it('shows raw zone selected by default with its pipelines', () => {
    render(<DataExplorer />);
    // raw zone is active - verify pipeline folders appear in file browser
    expect(screen.getByText('ecommerce-events/')).toBeInTheDocument();
    expect(screen.getByText('iot-sensors/')).toBeInTheDocument();
    expect(screen.getByText('web-analytics/')).toBeInTheDocument();
  });

  it('shows file counts in the file browser for raw zone', () => {
    render(<DataExplorer />);
    expect(screen.getByText('312 files')).toBeInTheDocument();
    expect(screen.getByText('380 files')).toBeInTheDocument();
    expect(screen.getByText('200 files')).toBeInTheDocument();
  });

  it('clicking clean zone updates file browser with clean data', () => {
    render(<DataExplorer />);
    fireEvent.click(screen.getByText('clean'));

    // Clean zone file counts
    expect(screen.getByText('298 files')).toBeInTheDocument();
    expect(screen.getByText('365 files')).toBeInTheDocument();
    expect(screen.getByText('189 files')).toBeInTheDocument();
  });

  it('clicking agg zone updates file browser with agg data', () => {
    render(<DataExplorer />);
    fireEvent.click(screen.getByText('agg'));

    // Agg zone file counts
    expect(screen.getByText('156 files')).toBeInTheDocument();
    expect(screen.getByText('192 files')).toBeInTheDocument();
    expect(screen.getByText('98 files')).toBeInTheDocument();
  });

  it('clicking a pipeline folder shows sample partitions', () => {
    render(<DataExplorer />);
    // Click ecommerce-events folder
    const folder = screen.getByText('ecommerce-events/').closest('button');
    fireEvent.click(folder);

    expect(screen.getByText('Sample Partitions')).toBeInTheDocument();
    expect(screen.getByText('year=2026/month=09/day=18/')).toBeInTheDocument();
    expect(screen.getByText('year=2026/month=09/day=17/')).toBeInTheDocument();
  });

  it('renders parquet file names in expanded partition view', () => {
    render(<DataExplorer />);
    const folder = screen.getByText('ecommerce-events/').closest('button');
    fireEvent.click(folder);

    expect(screen.getByText('run-a1b2c3d4e5f6.parquet')).toBeInTheDocument();
    expect(screen.getByText('run-f6e5d4c3b2a1.parquet')).toBeInTheDocument();
  });

  it('renders Storage by Zone chart section', () => {
    render(<DataExplorer />);
    expect(screen.getByText('Storage by Zone')).toBeInTheDocument();
  });

  it('renders Data Format info section', () => {
    render(<DataExplorer />);
    expect(screen.getByText('Data Format')).toBeInTheDocument();
    expect(screen.getByText('Apache Parquet')).toBeInTheDocument();
    expect(screen.getByText('Snappy Compression')).toBeInTheDocument();
    expect(screen.getByText('Date Partitioned')).toBeInTheDocument();
    expect(screen.getByText('Glue Catalog')).toBeInTheDocument();
  });

  it('toggling a pipeline folder off hides partitions', () => {
    render(<DataExplorer />);

    // Open
    const openBtn = screen.getByText('ecommerce-events/').closest('button');
    fireEvent.click(openBtn);
    expect(screen.getByText('Sample Partitions')).toBeInTheDocument();

    // Close by clicking the same pipeline button again
    const closeBtn = screen.getByText('ecommerce-events/').closest('button');
    fireEvent.click(closeBtn);
    expect(screen.queryByText('Sample Partitions')).not.toBeInTheDocument();
  });
});
