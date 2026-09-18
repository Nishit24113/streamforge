import { useState } from 'react';
import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import { AlertTriangle, Shield, Clock, Flame, Filter } from 'lucide-react';
import { getAnomalies } from '../utils/api';

export default function AnomalyTimeline() {
  const [selectedPipeline, setSelectedPipeline] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['anomalies', selectedPipeline],
    queryFn: () => getAnomalies(selectedPipeline || undefined),
    refetchInterval: 30000,
  });

  const anomalies = data?.anomalies || [];

  const scatterData = anomalies.map((a) => ({
    time: new Date(a.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    score: parseFloat(a.anomaly_score),
    severity: a.severity,
    pipeline: a.pipeline_id,
    event_type: a.event_type,
    timestamp: a.timestamp,
  }));

  const highCount = anomalies.filter(a => a.severity === 'HIGH').length;
  const mediumCount = anomalies.filter(a => a.severity === 'MEDIUM').length;
  const avgScore = anomalies.length > 0
    ? (anomalies.reduce((sum, a) => sum + parseFloat(a.anomaly_score), 0) / anomalies.length).toFixed(3)
    : '0.000';

  const container = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.06 } },
  };
  const item = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 },
  };

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Total Anomalies', value: anomalies.length, icon: AlertTriangle, color: 'text-amber-400', bg: 'bg-amber-500/10' },
          { label: 'High Severity', value: highCount, icon: Flame, color: 'text-red-400', bg: 'bg-red-500/10' },
          { label: 'Medium Severity', value: mediumCount, icon: Shield, color: 'text-amber-400', bg: 'bg-amber-500/10' },
          { label: 'Avg Score', value: avgScore, icon: Clock, color: 'text-forge-400', bg: 'bg-forge-500/10' },
        ].map((card) => {
          const Icon = card.icon;
          return (
            <motion.div key={card.label} variants={item} className="glass-card p-4">
              <div className={`inline-flex p-2 rounded-lg ${card.bg} mb-2`}>
                <Icon className={`w-4 h-4 ${card.color}`} />
              </div>
              <p className="text-2xl font-bold text-white">{card.value}</p>
              <p className="text-xs text-gray-400">{card.label}</p>
            </motion.div>
          );
        })}
      </div>

      {/* Filter */}
      <motion.div variants={item} className="flex items-center gap-3">
        <Filter className="w-4 h-4 text-gray-400" />
        <select
          value={selectedPipeline}
          onChange={(e) => setSelectedPipeline(e.target.value)}
          className="px-3 py-2 bg-gray-800/50 border border-gray-700 rounded-lg text-sm text-white focus:ring-2 focus:ring-forge-500 focus:border-transparent"
        >
          <option value="">All Pipelines</option>
          <option value="ecommerce-events">E-Commerce</option>
          <option value="iot-sensors">IoT Sensors</option>
          <option value="web-analytics">Web Analytics</option>
        </select>
      </motion.div>

      {/* Scatter Chart */}
      <motion.div variants={item} className="glass-card p-6">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">Anomaly Score Timeline</h3>
        <ResponsiveContainer width="100%" height={300}>
          <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="time" stroke="#64748b" fontSize={11} />
            <YAxis dataKey="score" stroke="#64748b" fontSize={11} domain={[0.5, 1]} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '12px',
                fontSize: '12px',
              }}
              formatter={(value, name) => [parseFloat(value).toFixed(4), name]}
            />
            <Scatter data={scatterData} name="Anomaly Score">
              {scatterData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.severity === 'HIGH' ? '#ef4444' : '#f59e0b'}
                  fillOpacity={0.8}
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </motion.div>

      {/* Anomaly List */}
      <motion.div variants={item} className="glass-card overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-800/50">
          <h3 className="text-sm font-semibold text-gray-300">Recent Anomalies</h3>
        </div>
        <div className="divide-y divide-gray-800/30">
          {anomalies.slice(0, 15).map((anomaly) => (
            <motion.div
              key={anomaly.alert_id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className={`flex items-center justify-between px-6 py-3 hover:bg-gray-800/20 transition-colors ${
                anomaly.severity === 'HIGH' ? 'border-l-2 border-l-red-500' : 'border-l-2 border-l-amber-500'
              }`}
            >
              <div className="flex items-center gap-4">
                <div className={`w-2 h-2 rounded-full ${
                  anomaly.severity === 'HIGH' ? 'bg-red-500 anomaly-pulse' : 'bg-amber-500'
                }`} />
                <div>
                  <p className="text-sm text-white font-medium">{anomaly.event_type}</p>
                  <p className="text-xs text-gray-500">{anomaly.pipeline_id}</p>
                </div>
              </div>
              <div className="flex items-center gap-6">
                <span className={`text-sm font-mono ${
                  anomaly.severity === 'HIGH' ? 'text-red-400' : 'text-amber-400'
                }`}>
                  {parseFloat(anomaly.anomaly_score).toFixed(4)}
                </span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  anomaly.severity === 'HIGH'
                    ? 'bg-red-500/10 text-red-400'
                    : 'bg-amber-500/10 text-amber-400'
                }`}>
                  {anomaly.severity}
                </span>
                <span className="text-xs text-gray-500">
                  {new Date(anomaly.timestamp).toLocaleTimeString()}
                </span>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </motion.div>
  );
}
