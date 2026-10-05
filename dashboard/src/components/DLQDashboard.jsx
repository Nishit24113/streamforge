import React, { useState, useEffect } from 'react';
import { LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

/**
 * Dead-Letter Queue Metrics Dashboard
 *
 * Shows failure trends, breakdown by reason, and replay recovery rate.
 */

const REASON_COLORS = {
  schema_validation: '#F59E0B',
  transform_error: '#EF4444',
  downstream_timeout: '#8B5CF6',
  throttled: '#3B82F6',
  unknown: '#6B7280'
};

const REASON_LABELS = {
  schema_validation: 'Schema Validation',
  transform_error: 'Transform Error',
  downstream_timeout: 'Downstream Timeout',
  throttled: 'Throttled',
  unknown: 'Unknown'
};

const DLQDashboard = ({ pipelineId }) => {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [windowHours, setWindowHours] = useState(24);

  useEffect(() => {
    fetchSummary();
  }, [pipelineId, windowHours]);

  const fetchSummary = async () => {
    setLoading(true);
    try {
      const response = await fetch(
        `https://api.streamforge.com/dlq/${pipelineId}/metrics?hours=${windowHours}`
      );
      const data = await response.json();
      setSummary(data);
    } catch (error) {
      console.error('Error fetching DLQ metrics:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="p-6 text-white">Loading DLQ metrics...</div>;
  }

  if (!summary) {
    return <div className="p-6 text-white">Error loading DLQ metrics</div>;
  }

  const reasonData = Object.entries(summary.by_reason || {}).map(([reason, count]) => ({
    name: REASON_LABELS[reason] || reason,
    reason,
    value: count
  }));

  const trendData = (summary.trend || []).map(point => ({
    time: new Date(point.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
    failures: point.failures
  }));

  const recoveryPct = (summary.recovery?.recovery_rate || 0) * 100;

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold mb-2">Dead-Letter Queue Metrics</h1>
          <p className="text-gray-400">Failure trends and recovery for {pipelineId}</p>
        </div>
        <div className="flex gap-2">
          {[6, 24, 72, 168].map(h => (
            <button
              key={h}
              onClick={() => setWindowHours(h)}
              className={`px-3 py-2 rounded font-medium ${
                windowHours === h ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {h < 24 ? `${h}h` : `${h / 24}d`}
            </button>
          ))}
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <SummaryCard
          label="Total Failures"
          value={summary.total_failures.toLocaleString()}
          subtext={`Last ${windowHours}h`}
          highlight={summary.total_failures > 0}
        />
        <SummaryCard
          label="Top Failure Reason"
          value={summary.top_failure_reason ? REASON_LABELS[summary.top_failure_reason] : 'None'}
          subtext={summary.top_failure_reason ? `${summary.by_reason[summary.top_failure_reason]} events` : 'No failures'}
        />
        <SummaryCard
          label="Events Replayed"
          value={(summary.recovery?.replayed || 0).toLocaleString()}
          subtext={`${summary.recovery?.still_failing || 0} still failing`}
        />
        <SummaryCard
          label="Recovery Rate"
          value={`${recoveryPct.toFixed(1)}%`}
          subtext="Of replay attempts"
          highlight={recoveryPct >= 90}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-2 gap-4">
        {/* Failure Trend */}
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">Failure Trend</h3>
          {trendData.length === 0 ? (
            <div className="h-64 flex items-center justify-center text-gray-500">
              No failures in this window 🎉
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="time" stroke="#9CA3AF" fontSize={12} />
                <YAxis stroke="#9CA3AF" fontSize={12} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px' }}
                  labelStyle={{ color: '#F3F4F6' }}
                />
                <Line type="monotone" dataKey="failures" stroke="#EF4444" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Failures by Reason */}
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">Failures by Reason</h3>
          {reasonData.length === 0 ? (
            <div className="h-64 flex items-center justify-center text-gray-500">
              No failures to break down
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={reasonData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                  outerRadius={90}
                  dataKey="value"
                >
                  {reasonData.map((entry) => (
                    <Cell key={entry.reason} fill={REASON_COLORS[entry.reason] || '#6B7280'} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px' }}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Reason Breakdown Table */}
      {reasonData.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-4 mt-6">
          <h3 className="text-lg font-semibold mb-4">Breakdown</h3>
          <div className="space-y-2">
            {reasonData.sort((a, b) => b.value - a.value).map(item => {
              const pct = (item.value / summary.total_failures) * 100;
              return (
                <div key={item.reason} className="flex items-center gap-3">
                  <div className="w-40 text-sm">{item.name}</div>
                  <div className="flex-1 bg-gray-700 rounded-full h-4 overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${pct}%`, backgroundColor: REASON_COLORS[item.reason] || '#6B7280' }}
                    />
                  </div>
                  <div className="w-24 text-right text-sm text-gray-400">
                    {item.value.toLocaleString()} ({pct.toFixed(0)}%)
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

const SummaryCard = ({ label, value, subtext, highlight }) => (
  <div className={`rounded-lg p-4 ${highlight ? 'bg-blue-900/20 border border-blue-500/30' : 'bg-gray-800'}`}>
    <div className="text-sm text-gray-400 mb-1">{label}</div>
    <div className={`text-2xl font-bold mb-1 ${highlight ? 'text-blue-400' : 'text-white'}`}>
      {value}
    </div>
    <div className="text-xs text-gray-500">{subtext}</div>
  </div>
);

export default DLQDashboard;
