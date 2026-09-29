import React, { useState, useEffect } from 'react';
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

/**
 * Cost Optimization Dashboard
 *
 * Displays AWS spend breakdown, trends, anomalies, and actionable recommendations.
 */

const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'];

const CostDashboard = () => {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCostReport();
  }, []);

  const fetchCostReport = async () => {
    try {
      const response = await fetch('https://api.streamforge.com/cost/report');
      const data = await response.json();
      setReport(data);
    } catch (error) {
      console.error('Error fetching cost report:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="p-6 text-white">Loading cost data...</div>;
  }

  if (!report) {
    return <div className="p-6 text-white">Error loading cost data</div>;
  }

  const currentMonthCost = report.current_month.total;
  const last30DaysCost = report.last_30_days.total;
  const totalSavings = report.recommendations.reduce((sum, r) => sum + r.potential_savings, 0);

  // Prepare service cost data for pie chart
  const serviceCostData = Object.entries(report.current_month.by_service).map(([service, cost]) => ({
    name: service.replace('Amazon ', '').replace('AWS ', ''),
    value: parseFloat(cost.toFixed(2))
  })).sort((a, b) => b.value - a.value).slice(0, 6);

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Cost Optimization Dashboard</h1>
        <p className="text-gray-400">AWS spend analysis and savings recommendations</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <SummaryCard
          label="Current Month"
          value={`$${currentMonthCost.toFixed(2)}`}
          subtext={new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
        />
        <SummaryCard
          label="Last 30 Days"
          value={`$${last30DaysCost.toFixed(2)}`}
          subtext="Rolling window"
        />
        <SummaryCard
          label="Potential Savings"
          value={`$${totalSavings.toFixed(2)}`}
          subtext={`${report.recommendations.length} opportunities`}
          highlight
        />
        <SummaryCard
          label="Next Month Forecast"
          value={`$${report.forecast.forecast[0]?.forecast || 0}`}
          subtext="AI-powered prediction"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        {/* Cost Trend */}
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">30-Day Cost Trend</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={report.trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" stroke="#9CA3AF" fontSize={12} />
              <YAxis stroke="#9CA3AF" fontSize={12} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px' }}
                labelStyle={{ color: '#F3F4F6' }}
              />
              <Line type="monotone" dataKey="cost" stroke="#3B82F6" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Service Breakdown */}
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">Cost by Service</h3>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={serviceCostData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {serviceCostData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Cost Anomalies */}
      {report.anomalies.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-4 mb-6">
          <h3 className="text-lg font-semibold mb-4">⚠️ Cost Anomalies Detected</h3>
          <div className="space-y-3">
            {report.anomalies.map((anomaly, index) => (
              <div key={index} className="flex items-center justify-between p-3 bg-red-900/20 border border-red-500/30 rounded">
                <div>
                  <div className="font-semibold">{anomaly.service}</div>
                  <div className="text-sm text-gray-400">
                    {anomaly.date} • Expected: ${anomaly.expected_cost} • Actual: ${anomaly.actual_cost}
                  </div>
                </div>
                <div className="text-red-400 font-bold text-xl">
                  +${anomaly.impact}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Optimization Recommendations */}
      <div className="bg-gray-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">💡 Optimization Recommendations</h3>
          <div className="text-green-400 font-bold">
            Save up to ${totalSavings.toFixed(2)}/month
          </div>
        </div>
        <div className="space-y-3">
          {report.recommendations.map((rec, index) => (
            <RecommendationCard key={index} recommendation={rec} />
          ))}
        </div>
      </div>

      {/* Forecast */}
      <div className="bg-gray-800 rounded-lg p-4 mt-6">
        <h3 className="text-lg font-semibold mb-4">3-Month Cost Forecast</h3>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={report.forecast.forecast}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="month" stroke="#9CA3AF" fontSize={12} />
            <YAxis stroke="#9CA3AF" fontSize={12} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px' }}
              labelStyle={{ color: '#F3F4F6' }}
            />
            <Legend />
            <Bar dataKey="forecast" fill="#3B82F6" name="Forecast" />
            <Bar dataKey="lower_bound" fill="#10B981" name="Best Case" />
            <Bar dataKey="upper_bound" fill="#EF4444" name="Worst Case" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

const SummaryCard = ({ label, value, subtext, highlight }) => {
  return (
    <div className={`rounded-lg p-4 ${highlight ? 'bg-green-900/20 border border-green-500/30' : 'bg-gray-800'}`}>
      <div className="text-sm text-gray-400 mb-1">{label}</div>
      <div className={`text-2xl font-bold mb-1 ${highlight ? 'text-green-400' : 'text-white'}`}>
        {value}
      </div>
      <div className="text-xs text-gray-500">{subtext}</div>
    </div>
  );
};

const RecommendationCard = ({ recommendation }) => {
  const priorityColors = {
    high: 'border-red-500/30 bg-red-900/10',
    medium: 'border-yellow-500/30 bg-yellow-900/10',
    low: 'border-blue-500/30 bg-blue-900/10'
  };

  const priorityBadges = {
    high: 'bg-red-500 text-white',
    medium: 'bg-yellow-500 text-black',
    low: 'bg-blue-500 text-white'
  };

  return (
    <div className={`p-4 border rounded ${priorityColors[recommendation.priority]}`}>
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold">{recommendation.service}</span>
          <span className={`px-2 py-0.5 text-xs rounded-full ${priorityBadges[recommendation.priority]}`}>
            {recommendation.priority.toUpperCase()}
          </span>
        </div>
        <div className="text-green-400 font-bold">
          Save ${recommendation.potential_savings}/mo
        </div>
      </div>
      <div className="text-sm text-gray-300 mb-2">
        <span className="font-semibold">Issue:</span> {recommendation.issue}
      </div>
      <div className="text-sm text-gray-300">
        <span className="font-semibold">Recommendation:</span> {recommendation.recommendation}
      </div>
    </div>
  );
};

export default CostDashboard;
