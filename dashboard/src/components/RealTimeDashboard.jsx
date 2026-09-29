import React, { useState, useEffect, useRef } from 'react';
import { LineChart, Line, AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

/**
 * Real-Time WebSocket Dashboard
 *
 * Live streaming metrics with WebSocket connection to backend.
 * Updates every second with new events, anomalies, and throughput data.
 */

const RealTimeDashboard = ({ pipelineId }) => {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState([]);
  const [metrics, setMetrics] = useState({
    eventsPerSecond: 0,
    anomalyRate: 0,
    avgLatency: 0,
    activeConnections: 0
  });
  const [throughputData, setThroughputData] = useState([]);
  const [anomalyData, setAnomalyData] = useState([]);
  const ws = useRef(null);
  const maxDataPoints = 60; // Keep last 60 seconds

  useEffect(() => {
    // Connect to WebSocket
    const wsUrl = `wss://api.streamforge.com/realtime?pipeline=${pipelineId}`;
    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      console.log('WebSocket connected');
      setConnected(true);
    };

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'event') {
        // Add new event to stream
        setEvents((prev) => [data.event, ...prev].slice(0, 100));
      } else if (data.type === 'metrics') {
        // Update real-time metrics
        setMetrics(data.metrics);

        // Update throughput chart
        setThroughputData((prev) => {
          const newData = [...prev, {
            timestamp: new Date().toLocaleTimeString(),
            events: data.metrics.eventsPerSecond,
            anomalies: data.metrics.anomaliesPerSecond || 0
          }];
          return newData.slice(-maxDataPoints);
        });

        // Update anomaly rate chart
        setAnomalyData((prev) => {
          const newData = [...prev, {
            timestamp: new Date().toLocaleTimeString(),
            rate: data.metrics.anomalyRate * 100
          }];
          return newData.slice(-maxDataPoints);
        });
      }
    };

    ws.current.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnected(false);
    };

    ws.current.onclose = () => {
      console.log('WebSocket disconnected');
      setConnected(false);
    };

    // Cleanup on unmount
    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [pipelineId]);

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">Real-Time Pipeline Monitor</h1>
        <div className="flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'} animate-pulse`}></div>
          <span className="text-sm">{connected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </div>

      {/* Live Metrics Cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <MetricCard
          label="Events/sec"
          value={metrics.eventsPerSecond}
          unit="eps"
          trend={metrics.eventsPerSecond > 100 ? 'up' : 'stable'}
        />
        <MetricCard
          label="Anomaly Rate"
          value={(metrics.anomalyRate * 100).toFixed(2)}
          unit="%"
          trend={metrics.anomalyRate > 0.05 ? 'up' : 'down'}
        />
        <MetricCard
          label="Avg Latency"
          value={metrics.avgLatency}
          unit="ms"
          trend={metrics.avgLatency < 100 ? 'down' : 'up'}
        />
        <MetricCard
          label="Active Connections"
          value={metrics.activeConnections}
          unit=""
          trend="stable"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        {/* Throughput Chart */}
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">Live Throughput</h3>
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={throughputData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="timestamp" stroke="#9CA3AF" fontSize={12} />
              <YAxis stroke="#9CA3AF" fontSize={12} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px' }}
                labelStyle={{ color: '#F3F4F6' }}
              />
              <Area type="monotone" dataKey="events" stroke="#3B82F6" fill="#3B82F6" fillOpacity={0.6} />
              <Area type="monotone" dataKey="anomalies" stroke="#EF4444" fill="#EF4444" fillOpacity={0.4} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Anomaly Rate Chart */}
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">Anomaly Rate (%)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={anomalyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="timestamp" stroke="#9CA3AF" fontSize={12} />
              <YAxis stroke="#9CA3AF" fontSize={12} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px' }}
                labelStyle={{ color: '#F3F4F6' }}
              />
              <Line type="monotone" dataKey="rate" stroke="#F59E0B" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Live Event Stream */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-lg font-semibold mb-4">Live Event Stream</h3>
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {events.length === 0 ? (
            <div className="text-gray-400 text-center py-8">
              Waiting for events...
            </div>
          ) : (
            events.map((event, index) => (
              <EventRow key={`${event.id}-${index}`} event={event} />
            ))
          )}
        </div>
      </div>
    </div>
  );
};

const MetricCard = ({ label, value, unit, trend }) => {
  const trendColors = {
    up: 'text-red-400',
    down: 'text-green-400',
    stable: 'text-gray-400'
  };

  const trendIcons = {
    up: '↑',
    down: '↓',
    stable: '→'
  };

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="text-sm text-gray-400 mb-1">{label}</div>
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-bold">{value}</span>
        <span className="text-sm text-gray-400">{unit}</span>
        <span className={`text-sm ${trendColors[trend]} ml-auto`}>
          {trendIcons[trend]}
        </span>
      </div>
    </div>
  );
};

const EventRow = ({ event }) => {
  return (
    <div className={`flex items-center gap-4 p-3 rounded ${event.isAnomaly ? 'bg-red-900/20 border border-red-500/30' : 'bg-gray-700/50'}`}>
      {/* Timestamp */}
      <div className="text-xs text-gray-400 w-20">
        {new Date(event.timestamp).toLocaleTimeString()}
      </div>

      {/* Event Type */}
      <div className="text-sm font-mono bg-gray-700 px-2 py-1 rounded">
        {event.eventType}
      </div>

      {/* Source */}
      <div className="text-sm text-gray-300">
        {event.source}
      </div>

      {/* Anomaly Badge */}
      {event.isAnomaly && (
        <div className="ml-auto">
          <span className="px-2 py-1 bg-red-500 text-white text-xs rounded-full">
            ANOMALY {(event.anomalyScore * 100).toFixed(1)}%
          </span>
        </div>
      )}

      {/* Payload Preview */}
      <div className="text-xs text-gray-400 ml-auto font-mono max-w-xs truncate">
        {JSON.stringify(event.payload).substring(0, 50)}...
      </div>
    </div>
  );
};

export default RealTimeDashboard;
