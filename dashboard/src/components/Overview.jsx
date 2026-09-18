import { motion } from 'framer-motion';
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts';
import { Database, Activity, AlertTriangle, CheckCircle2, XCircle, TrendingUp } from 'lucide-react';

const COLORS = ['#2e88ff', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

function generateTimeSeriesData() {
  const data = [];
  const now = Date.now();
  for (let i = 23; i >= 0; i--) {
    const hour = new Date(now - i * 3600000);
    data.push({
      time: hour.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      events: Math.floor(Math.random() * 8000) + 2000,
      anomalies: Math.floor(Math.random() * 80) + 5,
    });
  }
  return data;
}

function generatePipelineThroughput() {
  return [
    { name: 'E-Commerce', events: 98450, anomalies: 523 },
    { name: 'IoT Sensors', events: 112340, anomalies: 487 },
    { name: 'Web Analytics', events: 37103, anomalies: 237 },
  ];
}

function generateAnomalyDistribution() {
  return [
    { name: 'High', value: 127, fill: '#ef4444' },
    { name: 'Medium', value: 843, fill: '#f59e0b' },
    { name: 'Low', value: 277, fill: '#10b981' },
  ];
}

function generateLatencyData() {
  const data = [];
  const now = Date.now();
  for (let i = 11; i >= 0; i--) {
    const hour = new Date(now - i * 3600000);
    data.push({
      time: hour.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      p50: Math.floor(Math.random() * 50) + 20,
      p95: Math.floor(Math.random() * 200) + 100,
      p99: Math.floor(Math.random() * 500) + 200,
    });
  }
  return data;
}

const timeSeriesData = generateTimeSeriesData();
const pipelineThroughput = generatePipelineThroughput();
const anomalyDist = generateAnomalyDistribution();
const latencyData = generateLatencyData();

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.08 } },
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
};

export default function Overview({ stats }) {
  const s = stats || {
    total_events: 247893,
    total_anomalies: 1247,
    total_runs: 892,
    completed_runs: 856,
    failed_runs: 12,
    active_pipelines: 3,
    anomaly_rate: 0.5,
  };

  const statCards = [
    {
      label: 'Total Events',
      value: s.total_events?.toLocaleString() || '0',
      icon: Database,
      color: 'from-forge-500 to-blue-600',
      bgColor: 'bg-forge-500/10',
    },
    {
      label: 'Pipeline Runs',
      value: s.total_runs?.toLocaleString() || '0',
      icon: Activity,
      color: 'from-emerald-500 to-green-600',
      bgColor: 'bg-emerald-500/10',
    },
    {
      label: 'Anomalies Detected',
      value: s.total_anomalies?.toLocaleString() || '0',
      icon: AlertTriangle,
      color: 'from-amber-500 to-orange-600',
      bgColor: 'bg-amber-500/10',
    },
    {
      label: 'Success Rate',
      value: s.total_runs > 0
        ? `${((s.completed_runs / s.total_runs) * 100).toFixed(1)}%`
        : '99.9%',
      icon: CheckCircle2,
      color: 'from-emerald-500 to-teal-600',
      bgColor: 'bg-emerald-500/10',
    },
    {
      label: 'Failed Runs',
      value: s.failed_runs?.toString() || '0',
      icon: XCircle,
      color: 'from-red-500 to-rose-600',
      bgColor: 'bg-red-500/10',
    },
    {
      label: 'Anomaly Rate',
      value: `${s.anomaly_rate || 0.5}%`,
      icon: TrendingUp,
      color: 'from-violet-500 to-purple-600',
      bgColor: 'bg-violet-500/10',
    },
  ];

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="space-y-6">
      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {statCards.map((card, i) => {
          const Icon = card.icon;
          return (
            <motion.div
              key={card.label}
              variants={item}
              whileHover={{ scale: 1.03, y: -4 }}
              className="glass-card stat-glow p-4"
            >
              <div className={`inline-flex p-2 rounded-lg ${card.bgColor} mb-3`}>
                <Icon className={`w-5 h-5 bg-gradient-to-r ${card.color} bg-clip-text`}
                  style={{ color: COLORS[i % COLORS.length] }} />
              </div>
              <p className="text-2xl font-bold text-white">{card.value}</p>
              <p className="text-xs text-gray-400 mt-1">{card.label}</p>
            </motion.div>
          );
        })}
      </div>

      {/* Charts Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Event Throughput */}
        <motion.div variants={item} className="glass-card p-6">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Event Throughput (24h)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={timeSeriesData}>
              <defs>
                <linearGradient id="colorEvents" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#2e88ff" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#2e88ff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="time" stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={11} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '12px',
                  fontSize: '12px',
                }}
              />
              <Area
                type="monotone"
                dataKey="events"
                stroke="#2e88ff"
                strokeWidth={2}
                fill="url(#colorEvents)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </motion.div>

        {/* Pipeline Throughput */}
        <motion.div variants={item} className="glass-card p-6">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Pipeline Throughput</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={pipelineThroughput} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis type="number" stroke="#64748b" fontSize={11} />
              <YAxis dataKey="name" type="category" stroke="#64748b" fontSize={11} width={100} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '12px',
                  fontSize: '12px',
                }}
              />
              <Bar dataKey="events" fill="#2e88ff" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </motion.div>
      </div>

      {/* Charts Row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Processing Latency */}
        <motion.div variants={item} className="glass-card p-6 lg:col-span-2">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Processing Latency (ms)</h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={latencyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="time" stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={11} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '12px',
                  fontSize: '12px',
                }}
              />
              <Line type="monotone" dataKey="p50" stroke="#10b981" strokeWidth={2} dot={false} name="p50" />
              <Line type="monotone" dataKey="p95" stroke="#f59e0b" strokeWidth={2} dot={false} name="p95" />
              <Line type="monotone" dataKey="p99" stroke="#ef4444" strokeWidth={2} dot={false} name="p99" />
            </LineChart>
          </ResponsiveContainer>
          <div className="flex items-center gap-6 mt-3">
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <div className="w-3 h-0.5 bg-emerald-500 rounded" /> p50
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <div className="w-3 h-0.5 bg-amber-500 rounded" /> p95
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <div className="w-3 h-0.5 bg-red-500 rounded" /> p99
            </div>
          </div>
        </motion.div>

        {/* Anomaly Distribution */}
        <motion.div variants={item} className="glass-card p-6">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Anomaly Severity</h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={anomalyDist}
                cx="50%"
                cy="50%"
                innerRadius={55}
                outerRadius={80}
                paddingAngle={4}
                dataKey="value"
              >
                {anomalyDist.map((entry, index) => (
                  <Cell key={entry.name} fill={entry.fill} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '12px',
                  fontSize: '12px',
                }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-4 mt-2">
            {anomalyDist.map((d) => (
              <div key={d.name} className="flex items-center gap-1.5 text-xs text-gray-400">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: d.fill }} />
                {d.name} ({d.value})
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}
